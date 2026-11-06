#!/usr/bin/env python3
"""行区间提取工具：从（大）文件中抽取部分行。

支持三种互斥的抽取方式，配合拆分工具可做抽样：
    1. --range M:N   第 M 到第 N 行（1 起始、含端点，支持 :N / M: 开区间）
    2. --every K     每第 K 行（即第 K, 2K, 3K ... 行）
    3. --match RE    匹配正则的行；--blocks "RE_A:RE_B" 抽取从匹配 A 的行
                     到匹配 B 的行（含端点）的所有区间

用法:
    python extract-line-range.py big.txt --range 100:200 [-o out.txt]
    python extract-line-range.py big.txt --every 10 [-o out.txt]
    python extract-line-range.py big.txt --match "ERROR" [-o out.txt]
    python extract-line-range.py big.txt --blocks "BEGIN:END" [-o out.txt]

示例:
    python extract-line-range.py access.log --every 1000 | wc -l
    python extract-line-range.py log.txt --blocks "^BEGIN:^END$" -o region.txt

说明:
    - 流式逐行处理，内存占用与文件大小无关，适合大文件。
    - 行号从 1 开始；--range 开放端：":50" 表示前 50 行，"100:" 表示
      第 100 行到文件末尾。
    - 输出默认标准输出，-o 写文件。
只使用 Python 标准库。
"""

import argparse
import os
import re
import sys


def parse_range(s):
    m = re.fullmatch(r"(\d*):(\d*)", s.strip())
    if not m or (not m.group(1) and not m.group(2)):
        raise SystemExit('error: --range 形如 "M:N"、":N" 或 "M:"，M/N 为正整数')
    start = int(m.group(1)) if m.group(1) else 1
    end = int(m.group(2)) if m.group(2) else None
    if start < 1 or (end is not None and end < start):
        raise SystemExit("error: 要求 M >= 1 且 N >= M")
    return start, end


def parse_blocks(s):
    if s.count(":") != 1:
        raise SystemExit('error: --blocks 形如 "RE_A:RE_B"，用 ":" 分隔两个正则')
    a, b = s.split(":")
    try:
        return re.compile(a), re.compile(b)
    except re.error as e:
        raise SystemExit("error: --blocks 正则有误: %s" % e)


def main(argv=None):
    ap = argparse.ArgumentParser(description="从文件提取行区间/等距行/匹配行")
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--range", metavar="M:N",
                       help="第 M 到第 N 行（1 起始含端点，支持 :N / M:）")
    modes.add_argument("--every", type=int, metavar="K",
                       help="每第 K 行取一行")
    modes.add_argument("--match", metavar="RE", help="输出匹配正则的行")
    modes.add_argument("--blocks", metavar="RE_A:RE_B",
                       help="输出从匹配 A 的行到匹配 B 的行（含）的每个区间")
    ap.add_argument("input", help="输入文本文件")
    ap.add_argument("-o", "--out", default=None, help="输出文件（默认标准输出）")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.input):
        print("error: 输入文件不存在: %s" % args.input, file=sys.stderr)
        return 2

    start = end = None
    if args.range:
        start, end = parse_range(args.range)
    elif args.every is not None:
        if args.every < 1:
            print("error: --every 必须 >= 1", file=sys.stderr)
            return 2
    elif args.match is not None:
        try:
            match_re = re.compile(args.match)
        except re.error as e:
            print("error: --match 正则有误: %s" % e, file=sys.stderr)
            return 2
    else:
        block_a, block_b = parse_blocks(args.blocks)

    out_f = open(args.out, "w", encoding="utf-8", newline="\n") if args.out else sys.stdout
    lineno = 0
    picked = 0
    in_block = False
    try:
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                lineno += 1
                line = raw.rstrip("\n").rstrip("\r")
                take = False
                if args.range:
                    if lineno < start:
                        continue
                    if end is not None and lineno > end:
                        break
                    take = True
                elif args.every is not None:
                    take = (lineno % args.every == 0)
                elif args.match is not None:
                    take = match_re.search(line) is not None
                else:  # blocks
                    if not in_block and block_a.search(line):
                        in_block = True
                    if in_block:
                        take = True
                        if block_b.search(line):
                            in_block = False  # 区间闭合（含本行）
                if take:
                    out_f.write(line + "\n")
                    picked += 1
    finally:
        if out_f is not sys.stdout:
            out_f.close()

    msg = "picked %d line(s) from %d scanned" % (picked, lineno)
    if out_f is not sys.stdout:
        print("%s -> %s" % (msg, args.out))
    else:
        print(msg, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
