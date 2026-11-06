#!/usr/bin/env python3
"""fixed2csv.py -- 把定宽（fixed-width）报表文本解析为 CSV。

支持两种指定列边界的方式：
  1. 手工指定列位置范围，如 --cols "1-8,9-20,21-30"（1 起始，含两端）；
  2. 自动对齐分析（--auto，默认）：扫描所有行统计非空白字符的位置，
     找出全为空白的"间隙列"作为字段分隔，适合典型对齐报表。

用法:
    python fixed2csv.py report.txt -o out.csv
    python fixed2csv.py report.txt --cols "1-10,11-25,26-40"
    python fixed2csv.py report.txt --header-name "姓名,数量,金额"

参数:
    INPUT              输入文件路径；"-" 读 stdin
    -o, --output       输出 CSV 文件，缺省 stdout
    --cols             逗号分隔的列范围 "start-end"（1 起、含端点），逗号分隔多段
    --auto             强制自动对齐分析（缺省在未给 --cols 时启用）
    --min-gap          自动模式的最小空白间隙宽度，默认 2
    --skip             跳过开头行数（如标题/分隔线），默认 0
    -e, --encoding     输入编码，默认 utf-8

说明: 输出首行即原文本首行解析结果，可视为表头。

示例:
    python fixed2csv.py list.txt --cols "1-5,6-30,31-40" -o out.csv
    type list.txt | python fixed2csv.py - --auto
"""
import argparse
import csv
import io
import sys


def parse_cols(spec):
    """把 "1-8,9-20" 解析为 [(0,8),(8,20)] 的 0 基切片区间列表。"""
    ranges = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" not in part:
            raise SystemExit(f"错误: 列范围 {part!r} 缺少 '-'，应为 start-end")
        a, b = part.split("-", 1)
        try:
            s, e = int(a), int(b)
        except ValueError:
            raise SystemExit(f"错误: 列范围 {part!r} 含非整数")
        if s < 1 or e < s:
            raise SystemExit(f"错误: 列范围 {part!r} 无效（需 1<=start<=end）")
        ranges.append((s - 1, e))  # 0 基含端 -> 切片 end
    if not ranges:
        raise SystemExit("错误: --cols 为空")
    return ranges


def slice_by_cols(line, ranges):
    out = []
    for s, e in ranges:
        out.append(line[s:e].strip())
    return out


def auto_ranges(lines, min_gap=2):
    """自动对齐分析：非空字符所在位置为内容，连续 >= min_gap 的空白列为间隔。

    对每个空白间隙取中间作为切割点，返回区间列表。
    """
    if not lines:
        raise SystemExit("错误: 输入为空，无法自动分析")
    width = max(len(ln) for ln in lines)
    # occupied[i]: 该列是否出现过非空白字符
    occupied = [False] * width
    for ln in lines:
        for i, ch in enumerate(ln):
            if not ch.isspace():
                occupied[i] = True
    if not any(occupied):
        raise SystemExit("错误: 输入全是空白，无法自动分析")
    # 找连续空白段
    ranges = []
    in_field = False
    field_start = 0
    blank_run = 0
    for i in range(width):
        if occupied[i]:
            if not in_field:
                field_start = i
                in_field = True
            blank_run = 0
        else:
            if in_field:
                blank_run += 1
                # 间隙足够宽（或到达行尾）即切分
                if blank_run >= min_gap:
                    ranges.append((field_start, i - blank_run + 1))
                    in_field = False
                    blank_run = 0
    if in_field:
        ranges.append((field_start, width))
    if not ranges:
        raise SystemExit("错误: 未能分析出任何列，请用 --cols 手工指定")
    return ranges


def main():
    ap = argparse.ArgumentParser(
        description="把定宽报表文本解析为 CSV（列范围或自动对齐分析）")
    ap.add_argument("input", help="输入文件，或 '-' 表示 stdin")
    ap.add_argument("-o", "--output", help="输出 CSV 文件，缺省 stdout")
    ap.add_argument("--cols", help='列范围，如 "1-8,9-20,21-30"（1 起，含端点）')
    ap.add_argument("--auto", action="store_true", help="强制自动对齐分析")
    ap.add_argument("--min-gap", type=int, default=2,
                    help="自动模式最小空白间隙（默认 2）")
    ap.add_argument("--skip", type=int, default=0, help="跳过开头行数")
    ap.add_argument("-e", "--encoding", default="utf-8")
    args = ap.parse_args()

    if args.input == "-":
        text = sys.stdin.buffer.read().decode(args.encoding)
    else:
        try:
            with open(args.input, "r", encoding=args.encoding) as f:
                text = f.read()
        except OSError as exc:
            raise SystemExit(f"错误: 无法读取 {args.input}: {exc}")

    lines = text.splitlines()
    if args.skip:
        lines = lines[args.skip:]
    lines = [ln.rstrip("\r\n") for ln in lines]
    # 数据行通常不含纯空行；跳过空行
    lines = [ln for ln in lines if ln.strip()]

    if args.cols:
        ranges = parse_cols(args.cols)
        mode = f"指定列范围 {args.cols}"
    else:
        ranges = auto_ranges(lines, args.min_gap)
        mode = "自动对齐分析"

    rows = [slice_by_cols(ln, ranges) for ln in lines]

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerows(rows)
    out_text = out.getvalue()

    if args.output:
        with open(args.output, "w", encoding=args.encoding, newline="") as f:
            f.write(out_text)
        print(f"已写入 {args.output}（{len(rows)} 行 x {len(ranges)} 列，"
              f"模式: {mode}）", file=sys.stderr)
    else:
        sys.stdout.write(out_text)


if __name__ == "__main__":
    main()
