#!/usr/bin/env python3
"""文件行数排行 / file size rank.

对指定目录(默认只看一层, -r 递归)或文件按行数或字节数排序,
输出 Top N 排行榜(--asc 换成升序, 即最小的 N 个)。

行数按“显示行”统计: 换行符(LF)个数, 末行无换行时补 1, 空文件为 0;
统计与编码无关, 二进制文件也参与排行。

用法:
  python file-size-rank.py PATH... [-r] [-n N] [--by lines|bytes] [--asc]
      [--ext .py,.md] [--exclude NAME]...

示例:
  python file-size-rank.py src -r -n 10          # 行数最多的 10 个文件
  python file-size-rank.py src -r --by bytes     # 按字节数排行
  python file-size-rank.py src -r --asc -n 5     # 最小的 5 个

退出码: 0 = 正常; 2 = 路径/IO 错误。
"""

import argparse
import os
import sys
from pathlib import Path

DEFAULT_EXCLUDES = {".git"}


def parse_exts(text):
    if not text:
        return None
    exts = set()
    for token in text.replace(",", " ").split():
        token = token.strip().lower()
        if token:
            exts.add("." + token.lstrip("."))
    return exts or None


def match_ext(path, exts):
    return True if exts is None else path.suffix.lower() in exts


def collect(roots, recursive, exts, excludes):
    """返回 (文件列表, 错误消息列表); 显式给出的文件不做扩展名过滤。"""
    files, errors = [], []
    for root in roots:
        p = Path(root)
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            if recursive:
                for dirpath, dirnames, filenames in os.walk(p):
                    dirnames[:] = sorted(d for d in dirnames if d not in excludes)
                    for name in sorted(filenames):
                        if name in excludes:
                            continue
                        f = Path(dirpath, name)
                        if match_ext(f, exts):
                            files.append(f)
            else:
                try:
                    names = sorted(os.listdir(p))
                except OSError as exc:
                    errors.append(f"{p}: {exc}")
                    continue
                for name in names:
                    if name in excludes:
                        continue
                    f = p / name
                    if f.is_file() and match_ext(f, exts):
                        files.append(f)
        else:
            errors.append(f"路径不存在: {p}")
    return files, errors


def count_lines(path):
    """按 LF 换行符统计显示行数, 末行无换行补 1, 空文件为 0。"""
    total, tail = 0, b""
    with open(path, "rb") as fp:
        while True:
            chunk = fp.read(1 << 20)
            if not chunk:
                break
            total += chunk.count(b"\n")
            tail = chunk[-1:]
    if tail and tail != b"\n":
        total += 1
    return total


def hsize(num):
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        description="对目录/文件按行数或字节数排序, 输出 Top N 排行榜")
    ap.add_argument("paths", nargs="+", metavar="PATH", help="文件或目录(可多个)")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="递归遍历目录(默认只看一层)")
    ap.add_argument("-n", "--top", type=int, default=20,
                    help="排行榜条数(默认 20)")
    ap.add_argument("--by", choices=("lines", "bytes"), default="lines",
                    help="排序依据(默认 lines)")
    ap.add_argument("--asc", action="store_true", help="升序(默认降序)")
    ap.add_argument("--ext", default="", metavar="EXTS",
                    help="只统计这些扩展名(逗号分隔, 如 .py,.md); 显式给出的文件不受限")
    ap.add_argument("--exclude", action="append", default=[], metavar="NAME",
                    help="按名字跳过的目录或文件(可多次); 默认已跳过 .git")
    args = ap.parse_args(argv)

    excludes = DEFAULT_EXCLUDES | set(args.exclude)
    files, errors = collect(args.paths, args.recursive, parse_exts(args.ext), excludes)

    rows = []
    for f in files:
        try:
            rows.append((f, count_lines(f), f.stat().st_size))
        except OSError as exc:
            errors.append(f"{f}: {exc}")

    by_lines = args.by == "lines"
    rows.sort(key=lambda r: str(r[0]))
    rows.sort(key=lambda r: r[1] if by_lines else r[2], reverse=not args.asc)
    top = max(0, args.top)
    total_lines = sum(r[1] for r in rows)
    total_bytes = sum(r[2] for r in rows)
    order = "升序" if args.asc else "降序"
    print(f"文件排行: 按{'行数' if by_lines else '字节数'}{order}, "
          f"前 {min(top, len(rows))} / 共 {len(rows)} 个文件, "
          f"合计 {total_lines:,} 行 / {hsize(total_bytes)}")
    for idx, (f, lines, size) in enumerate(rows[:top], 1):
        main_val = f"{lines:,} 行" if by_lines else hsize(size)
        sub_val = hsize(size) if by_lines else f"{lines:,} 行"
        print(f"{idx:>4}. {main_val:>14}  {sub_val:>12}  {f}")
    if len(rows) > top:
        print(f"(仅显示前 {top} 个, 其余 {len(rows) - top} 个未列出)")

    if errors:
        print(f"发生 {len(errors)} 个错误:", file=sys.stderr)
        for msg in errors:
            print(f"  {msg}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
