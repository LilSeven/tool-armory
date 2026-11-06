#!/usr/bin/env python3
"""有序归并：把多个已排序文本文件用堆归并为单个有序大文件（外部归并，内存友好）。

自行用 heapq 小顶堆做多路归并，任一时刻内存中只有每文件一行，适合大文件。
输入文件必须各自已按同样的顺序排好；--numeric 按行首整数比较，--reverse
用于降序输入。

用法:
    python merge-sorted.py sorted1.txt sorted2.txt -o merged.txt
    python merge-sorted.py n1.txt n2.txt -o merged.txt --numeric   # 按整数排序的输入
    python merge-sorted.py n1.txt n2.txt -o merged.txt --numeric --reverse  # 降序输入

参数:
    inputs       输入已排序文件（至少一个）
    -o, --output 输出文件（默认 stdout）
    --numeric    按行首整数值比较（即输入按整数排序）
    --reverse    输入为降序排列时使用

示例:
    python merge-sorted.py a.sorted b.sorted c.sorted -o all.sorted
"""
import argparse
import heapq
import os
import sys


def line_key(line, numeric):
    if numeric:
        return int(line.split(None, 1)[0])
    return line


def main(argv=None):
    ap = argparse.ArgumentParser(description="堆归并多个已排序文件为单个有序文件")
    ap.add_argument("inputs", nargs="+", help="输入已排序文件")
    ap.add_argument("-o", "--output", help="输出文件，缺省打印到 stdout")
    ap.add_argument("--numeric", action="store_true", help="按行首整数比较")
    ap.add_argument("--reverse", action="store_true", help="输入为降序")
    args = ap.parse_args(argv)

    # 降序输入：把键取反/反转后按升序归并
    def key(line):
        k = line_key(line, args.numeric)
        return -k if args.reverse else k

    handles = []
    files = []
    for p in args.inputs:
        if not os.path.isfile(p):
            print(f"警告: 跳过不存在的文件 {p}", file=sys.stderr)
            continue
        f = open(p, encoding="utf-8")
        handles.append(f)
        files.append(f)

    # 每个迭代器产出 (key, 序号i, 行号j, line)；i 仅用于键相等时稳定归并
    streams = []
    for i, f in enumerate(files):
        def gen(f=f, i=i):
            for j, line in enumerate(f):
                yield (key(line), i, j, line)
        streams.append(gen())

    out = open(args.output, "w", encoding="utf-8", newline="") if args.output else sys.stdout
    n = 0
    try:
        for _, _, _, line in heapq.merge(*streams):
            out.write(line if line.endswith("\n") else line + "\n")
            n += 1
    finally:
        for f in handles:
            f.close()
        if args.output:
            out.close()
    print(f"归并 {len(files)} 个文件，输出 {n} 行"
          f"（{'数值' if args.numeric else '字符串'}"
          f"{'降序' if args.reverse else '升序'}）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
