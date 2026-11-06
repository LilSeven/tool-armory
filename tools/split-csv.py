#!/usr/bin/env python3
"""拆分大 CSV：按行数切成多个分片，或按某列的值分组拆成多个文件，均保留表头。

两种模式:
    --lines N      每 N 个数据行一个分片，输出 <前缀>001.csv…
    --column 名/序号   按该列的值分组，每个值一个文件 <前缀>_<安全列值>.csv
所有分片的第一行都是原表头。仅用标准库 csv 模块。

用法:
    python split-csv.py <输入.csv> --lines 500 [-o 输出目录] [--prefix 前缀]
    python split-csv.py <输入.csv> --column region [-o 输出目录]
示例:
    python split-csv.py sales.csv --column region -o by_region/
    python split-csv.py big.csv --lines 10000
退出码: 0 成功；2 参数或文件错误。
"""
import argparse
import csv
import os
import re
import sys


def safe_name(value: str) -> str:
    """把列值转成安全的文件名片段。"""
    s = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", value.strip())
    return s.strip("._") or "_empty_"


def main() -> int:
    ap = argparse.ArgumentParser(description="按行数或按列值拆分 CSV（保留表头）")
    ap.add_argument("input", help="输入 CSV 文件")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--lines", type=int, help="每个分片的数据行数")
    g.add_argument("--column", help="按该列(名称或0基序号)的值分组拆分")
    ap.add_argument("-o", "--output", help="输出目录（默认 <输入名>.split/）")
    ap.add_argument("--prefix", help="输出文件名前缀（默认为输入文件名主干）")
    ap.add_argument("--encoding", default="utf-8-sig", help="输入编码（默认 utf-8-sig）")
    args = ap.parse_args()

    src = args.input
    if not os.path.isfile(src):
        print(f"错误: 输入文件不存在: {src}", file=sys.stderr)
        return 2
    if args.lines is not None and args.lines <= 0:
        print("错误: --lines 必须为正整数", file=sys.stderr)
        return 2

    out_dir = args.output or src + ".split"
    prefix = args.prefix or os.path.splitext(os.path.basename(src))[0]
    os.makedirs(out_dir, exist_ok=True)

    written = []  # (文件名, 行数)
    with open(src, "r", encoding=args.encoding, newline="") as fin:
        reader = csv.reader(fin)
        try:
            header = next(reader)
        except StopIteration:
            print("错误: 输入 CSV 为空", file=sys.stderr)
            return 2

        col_idx = None
        if args.column is not None:
            c = args.column.strip()
            if c.isdigit():
                col_idx = int(c)
                if col_idx >= len(header):
                    print(f"错误: 列序号 {col_idx} 超出表头范围", file=sys.stderr)
                    return 2
            else:
                try:
                    col_idx = header.index(c)
                except ValueError:
                    print(f"错误: 表头中找不到列: {c}", file=sys.stderr)
                    return 2

        if args.lines is not None:
            part_idx, count = 0, 0
            fout = None
            writer = None
            try:
                for row in reader:
                    if count % args.lines == 0:
                        if fout is not None:
                            fout.close()
                        part_idx += 1
                        name = f"{prefix}{part_idx:03d}.csv"
                        fout = open(os.path.join(out_dir, name), "w",
                                    encoding="utf-8", newline="")
                        writer = csv.writer(fout)
                        writer.writerow(header)
                        written.append((name, 0))
                    writer.writerow(row)
                    count += 1
                    written[-1] = (name, count - (part_idx - 1) * args.lines)
            finally:
                if fout is not None:
                    fout.close()
        else:
            groups = {}  # 值 -> writer
            files = {}
            counts = {}  # 值 -> 已写数据行数
            for row in reader:
                val = row[col_idx] if col_idx < len(row) else ""
                if val not in groups:
                    name = f"{prefix}_{safe_name(val)}.csv"
                    path = os.path.join(out_dir, name)
                    if name in files:
                        # 同名冲突（不同值清洗后同名），追加序号
                        k = 2
                        while True:
                            name = f"{prefix}_{safe_name(val)}_{k}.csv"
                            if name not in files:
                                break
                            k += 1
                        path = os.path.join(out_dir, name)
                    f = open(path, "w", encoding="utf-8", newline="")
                    w = csv.writer(f)
                    w.writerow(header)
                    groups[val] = w
                    files[name] = f
                    written.append((name, 0))
                    counts[val] = 0
                groups[val].writerow(row)
                counts[val] += 1
            for f in files.values():
                f.close()
            written = [(name, counts[val]) for val, (name, _) in
                       zip(list(groups.keys()), written)]

    for name, n in written:
        print(f"{name}  {n} 行数据")
    print(f"完成: {len(written)} 个分片, 输出目录 {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
