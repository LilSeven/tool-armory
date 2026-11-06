#!/usr/bin/env python3
"""定宽文本转 CSV：按列宽规格或自动检测对齐边界，把定宽(fixed-width)报表文本切分为 CSV。

用法:
    python fixed-width-to-csv.py report.txt -o out.csv
    python fixed-width-to-csv.py report.txt --cols 0-10,10-20,20-30
    python fixed-width-to-csv.py report.txt --header skip   # 首行是表头/分隔线，跳过
    python fixed-width-to-csv.py report.txt --header row    # 首行作为 CSV 表头
    python fixed-width-to-csv.py report.txt --colnames A,B,C --cols 0-10,10-20

说明:
    - --cols 用字符位置区间指定列（0 起，左闭右开），如 "0-10,10-20"。
    - 缺省自动检测：统计每个字符位置上空格出现的行占比，"几乎全为空格"的
      位置视为空白带；连续 >=2 列宽的空白带为列分隔，宽度为 1 的空白
      （通常是值内部的空格）并入所在列。
    - 空行自动跳过；字段内容去除首尾空白。

示例:
    python fixed-width-to-csv.py fw.txt -o fw.csv
"""

import argparse
import csv
import sys


def parse_cols(spec):
    """解析 "0-10,11-25" 为 [(start, end), ...]"""
    cols = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            start, end = int(a), int(b)
        else:
            start = int(part)
            end = start + 1
        if start < 0 or end <= start:
            raise ValueError("invalid column range: %r" % part)
        cols.append((start, end))
    return cols


def autodetect_cols(lines):
    """自动检测列边界。lines: 非空的原始行列表。"""
    if not lines:
        return []
    width = max(len(l) for l in lines)
    n = len(lines)
    tol = max(1, int(n * 0.1))  # 允许最多 10% 的行在该位置非空格
    blankish = []
    for x in range(width):
        spaces = sum(1 for l in lines if x < len(l) and l[x] == " ")
        blankish.append(spaces >= n - tol)

    segs = []
    x = 0
    while x < width:
        if not blankish[x]:
            s = x
            while x < width and not blankish[x]:
                x += 1
            segs.append([s, x])
        else:
            x += 1
    # 宽度为 1 的空白带视为值内空格，把相邻段合并
    merged = []
    for seg in segs:
        if merged and seg[0] - merged[-1][1] < 2:
            merged[-1][1] = seg[1]
        else:
            merged.append(seg)
    return [tuple(s) for s in merged]


def split_line(line, cols):
    out = []
    for start, end in cols:
        seg = line[start:end] if start < len(line) else ""
        out.append(seg.strip())
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="定宽报表文本转 CSV")
    ap.add_argument("input", help="输入定宽文本文件")
    ap.add_argument("-o", "--output", help="输出 CSV 文件（缺省打印到 stdout）")
    ap.add_argument("--cols", help='列位置规格，如 "0-10,10-20,20-30"（0 起，左闭右开）')
    ap.add_argument("--header", choices=["skip", "row"], default=None,
                    help="skip=跳过首行；row=首行作为 CSV 表头")
    ap.add_argument("--colnames", help="逗号分隔的列名（与 --cols/--header row 二选一）")
    args = ap.parse_args(argv)

    with open(args.input, "r", encoding="utf-8-sig", errors="replace") as f:
        raw_lines = f.read().splitlines()

    data_lines = [l for l in raw_lines if l.strip()]
    if not data_lines:
        print("no data lines", file=sys.stderr)
        return 1

    try:
        cols = parse_cols(args.cols) if args.cols else autodetect_cols(data_lines)
    except ValueError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    if not cols:
        print("autodetect found no columns; use --cols", file=sys.stderr)
        return 1

    rows = [split_line(l, cols) for l in data_lines]

    header = None
    if args.header == "skip":
        rows = rows[1:]
    elif args.header == "row":
        header = rows[0]
        rows = rows[1:]
    elif args.colnames:
        header = [c.strip() for c in args.colnames.split(",")]
        if len(header) != len(cols):
            print("warning: --colnames count (%d) != column count (%d)"
                  % (len(header), len(cols)), file=sys.stderr)

    if args.output:
        out = open(args.output, "w", encoding="utf-8-sig", newline="")
    else:
        out = sys.stdout
    try:
        w = csv.writer(out)
        if header:
            w.writerow(header)
        w.writerows(rows)
    finally:
        if args.output:
            out.close()
            print("written: %s (%d rows, %d cols)" % (args.output, len(rows), len(cols)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
