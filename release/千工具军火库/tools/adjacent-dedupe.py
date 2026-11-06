#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""相邻重复行去重——删除相邻重复行、压缩重复空行。

规则:
  1. 相邻完全相同的行只保留第一行（--ignore-case 时按 casefold 忽略大小写比较）;
  2. 连续空行默认压缩为一个空行（--blank squeeze, 含纯空白行, 一律视为空行）;
     --blank drop 删除全部空行; --blank keep 原样保留空行（仍受规则 1 约束）。
  其余行与行序不变。适合清理网络文本常见的重复粘贴段落与多余空行。

用法:
    python adjacent-dedupe.py input.txt -o output.txt --stats
    python adjacent-dedupe.py input.txt --blank drop -o output.txt
    python adjacent-dedupe.py input.txt --ignore-case -o output.txt
    python adjacent-dedupe.py input.txt > output.txt

退出码: 0=成功; 2=参数/文件错误。
"""

import argparse
import sys
from pathlib import Path


def _reconfig():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def die(msg):
    print(f"错误: {msg}", file=sys.stderr)
    sys.exit(2)


def read_text(path, encoding):
    raw = Path(path).read_bytes()
    if encoding != "auto":
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError) as exc:
            die(f"无法用 {encoding} 解码 {path}: {exc}")
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def write_text(path, text, encoding):
    with open(path, "w", encoding=encoding, newline="") as fh:
        fh.write(text)


def main(argv=None):
    _reconfig()
    ap = argparse.ArgumentParser(
        prog="adjacent-dedupe",
        description="删除相邻重复行与重复空行, 压缩网络文本的重复粘贴段落",
    )
    ap.add_argument("input", help="输入 TXT 文件")
    ap.add_argument("-o", "--output", help="输出文件; 缺省打印到 stdout")
    ap.add_argument("--blank", choices=("squeeze", "drop", "keep"), default="squeeze",
                    help="空行处理: squeeze=连续空行压成 1 个(默认), drop=全删, keep=保留")
    ap.add_argument("--ignore-case", action="store_true", help="比较时忽略大小写")
    ap.add_argument("--stats", action="store_true", help="在 stderr 打印统计")
    ap.add_argument("--encoding", default="auto", help="输入编码, auto=尝试 utf-8/gb18030/big5")
    ap.add_argument("--out-encoding", default="utf-8", help="输出文件编码（默认 utf-8）")
    args = ap.parse_args(argv)

    try:
        text = read_text(args.input, args.encoding)
    except OSError as exc:
        die(f"读取输入失败: {exc}")

    lines = text.splitlines()
    out = []
    last_key = object()  # 哨兵, 不会与任何字符串相等
    prev_blank = False
    removed_dup = removed_blank = 0

    for line in lines:
        if line.strip() == "":
            if args.blank == "drop":
                removed_blank += 1
                continue
            if args.blank == "squeeze":
                if prev_blank:
                    removed_blank += 1
                    continue
                out.append("")
                last_key = ""
                prev_blank = True
                continue
            # keep: 空行按普通行参与相邻去重
        else:
            prev_blank = False
        key = line.casefold() if args.ignore_case else line
        if key == last_key:
            removed_dup += 1
            continue
        out.append(line)
        last_key = key

    out_text = "\n".join(out) + ("\n" if out else "")
    if args.output:
        write_text(args.output, out_text, args.out_encoding)
        dest = args.output
    else:
        sys.stdout.write(out_text)
        dest = "<stdout>"

    if args.stats:
        print(f"[adjacent-dedupe] 输入 {len(lines)} 行, 去除相邻重复 {removed_dup} 行, "
              f"清理空行 {removed_blank} 行, 输出 {len(out)} 行 → {dest}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
