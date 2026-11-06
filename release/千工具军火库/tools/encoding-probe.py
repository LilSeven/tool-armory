#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""编码探测报告（encoding-probe）

通过 BOM 与 UTF-8 有效性检测推断文本文件的编码，并输出目录级编码分布汇总。

判定顺序:
  1. BOM -> utf-8-sig / utf-16-le / utf-16-be / utf-32-le / utf-32-be
  2. 按 UTF-8 严格解码成功 -> 全 ASCII 为 ascii，否则 utf-8
  3. 加 --guess 时依次尝试 gb18030 / big5 / shift_jis / euc-kr / euc-jp 严格解码
  4. 其余 -> unknown（无 BOM 的非 UTF-8 文件）
注意: 超过 --max-bytes 的大文件只检验前 --max-bytes 字节，结果带 sampled 标记；
      --guess 是启发式，个别编码之间（如 gb18030/big5）可能互相误判。

用法:
    python encoding-probe.py <目录或文件> [选项]

选项:
    --guess        对非 UTF-8 文件尝试常见东亚编码
    --max-bytes N  有效性检验的最大字节数（默认 8388608 = 8 MiB）
    --json         以 JSON 格式输出
    --hidden       包含以 . 开头的隐藏文件/目录

示例:
    python encoding-probe.py ./texts
    python encoding-probe.py ./texts --guess --json

仅使用 Python 标准库。
退出码: 0=扫描完成; 1=路径不存在; 2=参数错误。
"""

import argparse
import json
import os
import sys
from collections import Counter

# 长 BOM 放在前面，避免 utf-16 的 FF FE 抢先命中 utf-32-le
BOMS = [
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
]
GUESS_CHAIN = ("gb18030", "big5", "shift_jis", "euc-kr", "euc-jp")


def probe(data, guess):
    """返回 (encoding, via_bom, guessed)。"""
    if not data:
        return "empty", False, False
    for bom, enc in BOMS:
        if data.startswith(bom):
            return enc, True, False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    else:
        return ("ascii" if data.isascii() else "utf-8"), False, False
    if guess:
        for enc in GUESS_CHAIN:
            try:
                data.decode(enc)
            except UnicodeDecodeError:
                continue
            return enc, False, True
    return "unknown", False, False


def iter_files(root, include_hidden):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        if include_hidden:
            dirnames[:] = sorted(dirnames)
            names = sorted(filenames)
        else:
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            names = sorted(f for f in filenames if not f.startswith("."))
        for name in names:
            yield os.path.join(dirpath, name)


def trunc(s, n):
    return s if len(s) <= n else "..." + s[-(n - 3):]


def display(path, root):
    try:
        rel = os.path.relpath(path, root)
    except ValueError:
        return path
    return path if rel.startswith("..") else rel


def scan(root, max_bytes, guess, include_hidden):
    rows = []
    errors = []
    for path in iter_files(root, include_hidden):
        try:
            size = os.path.getsize(path)
            with open(path, "rb") as fh:
                data = fh.read(max_bytes)
        except OSError as exc:
            errors.append({"path": path, "error": str(exc)})
            continue
        enc, via_bom, guessed = probe(data, guess)
        rows.append({
            "path": path, "encoding": enc, "bom": via_bom, "guessed": guessed,
            "size": size, "sampled": size > len(data),
        })
    return rows, errors


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="encoding-probe",
        description="通过 BOM 与 UTF-8 有效性检测推断文本文件编码，汇总编码分布。",
    )
    parser.add_argument("path", help="要扫描的目录（或单个文件）")
    parser.add_argument("--guess", action="store_true",
                        help="对非 UTF-8 文件尝试常见东亚编码（gb18030/big5/shift_jis/euc-kr/euc-jp）")
    parser.add_argument("--max-bytes", type=int, default=8388608,
                        help="有效性检验的最大字节数（默认 8388608 = 8 MiB）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--hidden", action="store_true", help="包含隐藏文件/目录")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not os.path.exists(args.path):
        print("错误: 路径不存在: %s" % args.path, file=sys.stderr)
        return 1

    rows, errors = scan(args.path, max(4, args.max_bytes), args.guess, args.hidden)
    rows.sort(key=lambda r: r["path"])
    dist = Counter(r["encoding"] for r in rows)

    if args.json:
        payload = {
            "root": args.path,
            "total_files": len(rows),
            "distribution": dict(dist.most_common()),
            "guess": args.guess,
            "max_bytes": max(4, args.max_bytes),
            "read_errors": errors,
            "files": rows,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("扫描目标: %s   文件总数: %d（读取失败 %d，guess=%s）"
          % (args.path, len(rows), len(errors), args.guess))
    print()
    print("逐文件编码:")
    for r in rows:
        flags = []
        if r["bom"]:
            flags.append("BOM")
        if r["guessed"]:
            flags.append("guessed")
        if r["sampled"]:
            flags.append("sampled")
        print("  %-28s %-12s %s" % (
            trunc(display(r["path"], args.path), 28), r["encoding"],
            ("[" + ",".join(flags) + "]") if flags else ""))
    print()
    print("编码分布:")
    if rows:
        for enc, count in dist.most_common():
            pct = count * 100.0 / len(rows)
            bar = "#" * max(1, int(round(pct / 5)))
            print("  %-12s %3d %6.1f%%  %s" % (enc, count, pct, bar))
    else:
        print("  （无文件）")
    for err in errors:
        print("  [读取失败] %s: %s" % (err["path"], err["error"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
