#!/usr/bin/env python3
"""按行切分文件 (split-file-lines): 把大文件按行数或按分隔标记切成带序号的小文件，
逐行流式读写，无需全部载入内存。

用法:
  python -I split-file-lines.py -l LINES [-o PREFIX] [-e EXT] [FILE]
  python -I split-file-lines.py -p PATTERN [-o PREFIX] [-e EXT] [FILE]

选项:
  -l, --lines N       每个小文件的行数
  -p, --pattern RE    分隔标记正则：匹配到的行开启一个新文件（该行归新文件）
  -o, --prefix PREFIX 输出文件名前缀（默认取输入文件主名，stdin 下为 part）
  -e, --ext EXT       输出扩展名（默认 .txt）
  -w, --width N       序号补零位数（默认 4）
  FILE                输入文件；缺省或为 - 时读 stdin（此时须给 -o）

输出文件命名: PREFIX-0001.ext, PREFIX-0002.ext, ...（序号从 1 起）
-l 与 -p 必须二选一。切完在 stdout 打印每个输出文件及行数。

示例:
  python -I split-file-lines.py -l 2 -o part big.txt
  python -I split-file-lines.py -p '^### ' -o chunk doc.md
  cat big.log | python -I split-file-lines.py -l 100 -o piece
"""

import argparse
import os
import re
import sys

# Windows 控制台/管道下强制 UTF-8，避免 Git Bash 管道输入输出乱码
for _s in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="按行数或分隔标记把文件切成带序号的小文件")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("-l", "--lines", type=int, help="每个文件的行数")
    g.add_argument("-p", "--pattern", help="新文件分隔标记（正则）")
    ap.add_argument("-o", "--prefix", default=None, help="输出前缀")
    ap.add_argument("-e", "--ext", default=".txt", help="输出扩展名（默认 .txt）")
    ap.add_argument("-w", "--width", type=int, default=4, help="序号位数（默认 4）")
    ap.add_argument("file", nargs="?", default="-", help="输入文件，缺省读 stdin")
    args = ap.parse_args()

    if args.lines is not None and args.lines <= 0:
        ap.error("-l 必须为正整数")
    if args.pattern is not None:
        try:
            marker = re.compile(args.pattern)
        except re.error as e:
            ap.error(f"无效正则: {e}")
    else:
        marker = None

    if args.prefix is None:
        if args.file in ("-",) or not args.file:
            args.prefix = "part"
        else:
            args.prefix = os.path.splitext(os.path.basename(args.file))[0]
    if args.ext and not args.ext.startswith("."):
        args.ext = "." + args.ext

    if args.file in ("-",) or not args.file:
        stream = sys.stdin
    else:
        if not os.path.exists(args.file):
            print(f"split-file-lines: 文件不存在: {args.file}", file=sys.stderr)
            return 1
        stream = open(args.file, "r", encoding="utf-8", errors="replace")

    idx = 0          # 当前分片序号（0 表示尚未开片）
    wrote = 0        # 当前分片已写行数
    out = None
    out_name = ""
    summary = []
    exit_code = 0
    try:
        for line in stream:
            new_chunk = False
            if marker is not None:
                # 首个标记之前的行归入第 1 片（out is None 时强制开片）
                new_chunk = bool(marker.search(line)) or out is None
            else:  # 按行数
                new_chunk = (idx == 0 or wrote >= args.lines)
            if new_chunk:
                if out is not None:
                    out.close()
                    summary.append((out_name, wrote))
                idx += 1
                out_name = f"{args.prefix}-{idx:0{args.width}d}{args.ext}"
                out = open(out_name, "w", encoding="utf-8", newline="")
                wrote = 0
            out.write(line)
            wrote += 1
        if out is not None:
            out.close()
            summary.append((out_name, wrote))
        elif marker is not None:
            print("split-file-lines: 没有匹配到任何分隔标记，未生成文件", file=sys.stderr)
            exit_code = 1
    finally:
        if out is not None and not out.closed:
            out.close()
        if stream is not sys.stdin:
            stream.close()

    for name, n in summary:
        print(f"{name}\t{n} lines")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
