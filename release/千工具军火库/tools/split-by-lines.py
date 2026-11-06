#!/usr/bin/env python3
"""把文本文件按每 N 行拆成多个文件，文件名带序号前缀。

输出形如 <前缀>001.txt、<前缀>002.txt…（默认前缀为输入文件名）。
支持 -d/--dry-run 只统计不写盘。

用法:
    python split-by-lines.py <输入文件> -n <每份行数> [-o 输出目录] [--prefix 前缀]
示例:
    python split-by-lines.py access.log -n 1000 -o chunks/
选项:
    -n, --lines     每个输出文件的行数（默认 1000）
    -o, --output    输出目录（默认 <输入文件名>.lines/）
    --prefix        输出文件名前缀（默认为输入文件名不含路径）
    -d, --dry-run   只打印将要生成的分片，不实际写文件
退出码: 0 成功；2 参数或文件错误。
"""
import argparse
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description="按行数拆分文本文件")
    ap.add_argument("input", help="输入文本文件")
    ap.add_argument("-n", "--lines", type=int, default=1000, help="每份行数")
    ap.add_argument("-o", "--output", help="输出目录")
    ap.add_argument("--prefix", help="输出文件名前缀")
    ap.add_argument("-d", "--dry-run", action="store_true", help="只统计不写盘")
    args = ap.parse_args()

    src = args.input
    if not os.path.isfile(src):
        print(f"错误: 输入文件不存在: {src}", file=sys.stderr)
        return 2
    if args.lines <= 0:
        print("错误: 行数必须为正整数", file=sys.stderr)
        return 2

    out_dir = args.output or src + ".lines"
    prefix = args.prefix or os.path.splitext(os.path.basename(src))[0]

    def part_name(idx: int) -> str:
        return f"{prefix}{idx:03d}.txt"

    count = 0
    part_idx = 0
    fout = None
    try:
        with open(src, "r", encoding="utf-8", errors="replace", newline="") as fin:
            for line in fin:
                if count % args.lines == 0:
                    if fout is not None:
                        fout.close()
                    part_idx += 1
                    path = os.path.join(out_dir, part_name(part_idx))
                    print(f"{path}  起始行 {count + 1}")
                    if not args.dry_run:
                        os.makedirs(out_dir, exist_ok=True)
                        fout = open(path, "w", encoding="utf-8", newline="")
                if not args.dry_run:
                    fout.write(line)
                count += 1
    finally:
        if fout is not None:
            fout.close()

    parts = (count + args.lines - 1) // args.lines
    print(f"完成: 共 {count} 行, {parts} 个分片")
    return 0


if __name__ == "__main__":
    sys.exit(main())
