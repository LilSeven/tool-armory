#!/usr/bin/env python3
"""交错合并：把多个文件的行按轮转方式交错合并（每文件取一行轮转），支持按分隔符并排。

默认模式：第一轮取每个文件的第 1 行，第二轮取第 2 行……某文件读尽后跳过。
--side 模式：按行号把各文件对应行用分隔符拼接并排（较短文件补空字段）。

用法:
    python merge-interleave.py a.txt b.txt c.txt -o out.txt
    python merge-interleave.py a.txt b.txt --side -d "|" -o out.txt

参数:
    inputs       输入文件（至少一个）
    -o, --output 输出文件（默认 stdout）
    --side       并排模式：各文件同行号拼到一起
    -d, --delim  并排模式的分隔符（默认 \t；轮转模式忽略）

示例:
    # 轮转: 输出 a1 b1 c1 a2 b2 c2 ...
    python merge-interleave.py a.txt b.txt c.txt -o out.txt
    # 并排: 输出 "a1<tab>b1" 一行
    python merge-interleave.py a.txt b.txt --side
"""
import argparse
import itertools
import os
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(description="多文件行轮转交错合并或并排合并")
    ap.add_argument("inputs", nargs="+", help="输入文件")
    ap.add_argument("-o", "--output", help="输出文件，缺省打印到 stdout")
    ap.add_argument("--side", action="store_true", help="并排模式")
    ap.add_argument("-d", "--delim", default="\t", help="并排分隔符（默认制表符）")
    args = ap.parse_args(argv)

    paths = [p for p in args.inputs if os.path.isfile(p)]
    missing = [p for p in args.inputs if p not in paths]
    for p in missing:
        print(f"警告: 跳过不存在的文件 {p}", file=sys.stderr)
    if not paths:
        print("错误: 没有可用输入文件", file=sys.stderr)
        return 1

    def clean(f):
        for line in f:
            yield line.rstrip("\n").rstrip("\r")

    handles = [open(p, encoding="utf-8") for p in paths]
    out = open(args.output, "w", encoding="utf-8", newline="") if args.output else sys.stdout
    n = 0
    try:
        if args.side:
            cols = [clean(h) for h in handles]
            for row in itertools.zip_longest(*cols, fillvalue=""):
                out.write(args.delim.join(row) + "\n")
                n += 1
        else:
            iters = [clean(h) for h in handles]
            exhausted = [False] * len(iters)
            while not all(exhausted):
                for i, it in enumerate(iters):
                    if exhausted[i]:
                        continue
                    try:
                        out.write(next(it) + "\n")
                        n += 1
                    except StopIteration:
                        exhausted[i] = True
    finally:
        for h in handles:
            h.close()
        if args.output:
            out.close()
    print(f"输出 {n} 行（{len(paths)} 个文件，{'并排' if args.side else '轮转'}模式）",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
