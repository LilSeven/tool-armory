#!/usr/bin/env python3
"""行号增删 (line-numbers): 给文本行添加可配置格式的行号前缀，或反向剥离已有行号。

用法:
  python -I line-numbers.py [选项] [FILE]

选项:
  --start N     起始行号（默认 1）
  --step N      行号步长（默认 1）
  --width N     行号零填充到的位数；0 表示自动取最大行号位数（默认 0）
  --fmt TPL     行号模板，{n} 会被替换为行号（默认 '{n}'）
  --sep STR     行号与原文之间的分隔串（默认 '  '）
  --strip       剥离模式：删除默认样式的行号前缀 '^\\s*\\d+(?::|\\)|\\.)?\\s*'
  --strip-re PAT 剥离模式：按自定义正则 PAT 删除行号前缀（与 --strip 互斥）

FILE 缺省或为 - 时读 stdin，结果写 stdout。

示例:
  python -I line-numbers.py notes.txt
  python -I line-numbers.py --width 4 --fmt '[{n}]' --sep ' ' notes.txt
  python -I line-numbers.py --step 10 --start 0 --sep ': ' notes.txt
  python -I line-numbers.py --strip notes_numbered.txt
  python -I line-numbers.py --strip-re '^\\[\\d+\\] ' notes_numbered.txt
"""

import argparse
import re
import sys

DEFAULT_STRIP = r"^\s*\d+(?::|\)|\.)?\s*"

# Windows 控制台/管道下强制 UTF-8，避免 Git Bash 管道输入输出乱码
for _s in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="给文本行加行号前缀，或剥离已有行号")
    ap.add_argument("--start", type=int, default=1, help="起始行号（默认 1）")
    ap.add_argument("--step", type=int, default=1, help="步长（默认 1）")
    ap.add_argument("--width", type=int, default=0,
                    help="行号补零位数，0=自动（默认 0）")
    ap.add_argument("--fmt", default="{n}", help="行号模板，{n} 为行号（默认 '{n}'）")
    ap.add_argument("--sep", default="  ", help="行号后分隔串（默认两个空格）")
    ap.add_argument("--strip", action="store_true",
                    help="剥离默认样式的行号前缀")
    ap.add_argument("--strip-re", dest="strip_re", default=None, metavar="PATTERN",
                    help="剥离自定义正则匹配的行号前缀")
    ap.add_argument("file", nargs="?", default="-", help="输入文件，缺省读 stdin")
    args = ap.parse_args()

    if args.file == "-":
        stream = sys.stdin
    else:
        stream = open(args.file, "r", encoding="utf-8", errors="replace")

    exit_code = 0
    try:
        if args.strip or args.strip_re is not None:
            pat = re.compile(args.strip_re if args.strip_re is not None
                             else DEFAULT_STRIP)
            for raw in stream:
                print(pat.sub("", raw.rstrip("\r\n"), count=1))
        else:
            # 先数总行数以便自动补零（流式读两遍对 stdin 不可行，故 stdin 用计数器）。
            if args.width > 0:
                width = args.width
            elif args.file != "-":
                with open(args.file, "r", encoding="utf-8", errors="replace") as f:
                    nlines = sum(1 for _ in f)
                width = len(str(args.start + max(0, nlines - 1) * args.step))
            else:
                width = 0  # stdin 下未知行数，不做补零
            n = args.start
            for raw in stream:
                num = args.fmt.replace("{n}", str(n).zfill(width) if width else str(n))
                print(num + args.sep + raw.rstrip("\r\n"))
                n += args.step
    finally:
        if stream is not sys.stdin:
            stream.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
