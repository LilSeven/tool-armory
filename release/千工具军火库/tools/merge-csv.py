#!/usr/bin/env python3
"""CSV 合并：合并多个同构 CSV，对齐并去重表头，支持整行去重与来源文件名列。

把多个字段含义一致的 CSV 合并为一个大 CSV：读取各文件的表头，按出现顺序
对齐并去重得到统一表头；缺失的列以空值补齐。可选按整行去重，以及为每行
追加来源文件名列。

用法:
    python merge-csv.py a.csv b.csv -o merged.csv
    python merge-csv.py a.csv b.csv -o merged.csv --dedup --source-col src --encoding utf-8

参数:
    inputs          输入 CSV 文件（至少一个）
    -o, --output    输出文件路径（默认 stdout）
    --dedup         按整行内容去重（保留首次出现）
    --source-col    添加来源文件名列（传列名，如 src）
    --encoding      文件编码，默认 utf-8-sig
    --delimiter     CSV 分隔符，默认逗号

示例:
    # 合并同构 CSV 并去重、标记来源
    python merge-csv.py part1.csv part2.csv -o all.csv --dedup --source-col src
"""
import argparse
import csv
import os
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(description="合并多个同构 CSV（对齐去重表头）")
    ap.add_argument("inputs", nargs="+", help="输入 CSV 文件")
    ap.add_argument("-o", "--output", help="输出文件，缺省打印到 stdout")
    ap.add_argument("--dedup", action="store_true", help="按整行去重")
    ap.add_argument("--source-col", help="来源文件名列名")
    ap.add_argument("--encoding", default="utf-8-sig", help="文件编码（默认 utf-8-sig）")
    ap.add_argument("--delimiter", default=",", help="分隔符（默认 ,）")
    args = ap.parse_args(argv)

    header = []
    seen_header = set()
    rows = []
    seen_rows = set()
    n_dup = 0

    for path in args.inputs:
        if not os.path.isfile(path):
            print(f"警告: 跳过不存在的文件 {path}", file=sys.stderr)
            continue
        with open(path, newline="", encoding=args.encoding) as f:
            reader = csv.reader(f, delimiter=args.delimiter)
            try:
                head = next(reader)
            except StopIteration:
                continue  # 空文件
            for col in head:
                if col not in seen_header:
                    seen_header.add(col)
                    header.append(col)
            if args.source_col and args.source_col not in seen_header:
                seen_header.add(args.source_col)
                header.append(args.source_col)
            for row in reader:
                if not row:
                    continue
                # 对齐到统一表头：按各文件表头的列位置映射
                mapping = {name: i for i, name in enumerate(head)}
                full = [row[mapping[c]] if c in mapping and mapping[c] < len(row) else ""
                        for c in header if c != args.source_col]
                if args.source_col:
                    full.append(os.path.basename(path))
                if args.dedup:
                    key = tuple(full)
                    if key in seen_rows:
                        n_dup += 1
                        continue
                    seen_rows.add(key)
                rows.append(full)

    out = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout
    try:
        w = csv.writer(out, delimiter=args.delimiter)
        w.writerow(header)
        w.writerows(rows)
    finally:
        if args.output:
            out.close()
    print(f"合并 {len(args.inputs)} 个文件: {len(rows)} 行"
          + (f"，去重 {n_dup} 行" if args.dedup else ""),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
