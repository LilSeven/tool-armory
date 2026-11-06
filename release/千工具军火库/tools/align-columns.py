#!/usr/bin/env python3
"""文本列对齐 (align-columns): 按分隔符把松散文本的各行对齐成整齐的列。

中英文混排时用“显示宽度”计算填充：CJK/全角字符按 2 列计，其它按 1 列计，
保证在等宽字体终端下无论中英文，各列边界都能对齐。

用法:
  python -I align-columns.py [-d SEP] [-g GAP] [-r COL]... [FILE ...]

选项:
  -d, --delim SEP  列分隔符（字面量，支持写 \\t 表示制表符）；缺省按连续空白切分
  -g, --gap N      列间额外空格数（默认 2）
  -r, --right COL  把第 COL 列（1 起）改为右对齐，可多次出现
  FILE ...         输入文件；缺省或为 - 时读 stdin

示例:
  printf 'id name 描述\\n1 alice 张三\\n2 bob 李四王五\\n' | python -I align-columns.py
  python -I align-columns.py -d ',' -r 1 data.csv
  python -I align-columns.py -d '\\t' table.tsv
"""

import argparse
import re
import sys
import unicodedata

# Windows 控制台/管道下强制 UTF-8，避免 Git Bash 管道输入输出乱码
for _s in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def disp_width(s: str) -> int:
    """字符串的终端显示宽度（东亚全角/宽字符计 2，其余计 1）。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
               for ch in s)


def pad(s: str, width: int, right: bool = False) -> str:
    gap = " " * max(0, width - disp_width(s))
    return gap + s if right else s + gap


def main() -> int:
    ap = argparse.ArgumentParser(description="按分隔符对齐文本列（中英文混排按显示宽度计算）")
    ap.add_argument("-d", "--delim", default=None,
                    help="列分隔符，字面量，\\t 代表制表符；缺省按连续空白切分")
    ap.add_argument("-g", "--gap", type=int, default=2, help="列间空格数（默认 2）")
    ap.add_argument("-r", "--right", action="append", type=int, default=[],
                    metavar="COL", help="第几列右对齐（1 起），可重复")
    ap.add_argument("files", nargs="*", help="输入文件，缺省读 stdin")
    args = ap.parse_args()

    if args.delim is not None:
        delim = args.delim.replace("\\t", "\t")

        def split_line(line: str):
            return line.split(delim)
    else:
        def split_line(line: str):
            return line.split()

    right_cols = set(args.right)

    rows = []
    stream = sys.stdin if not args.files or "-" in args.files else open(
        args.files[0], "r", encoding="utf-8", errors="replace")
    try:
        for raw in stream:
            line = raw.rstrip("\r\n")
            cells = split_line(line)
            if cells:
                rows.append(cells)
    finally:
        if stream is not sys.stdin:
            stream.close()

    ncol = max((len(r) for r in rows), default=0)
    widths = [0] * ncol
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], disp_width(cell))

    for row in rows:
        parts = []
        for i in range(ncol):
            cell = row[i] if i < len(row) else ""
            parts.append(pad(cell, widths[i], right=(i + 1) in right_cols))
        print((" " * args.gap).join(parts).rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
