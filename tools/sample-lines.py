#!/usr/bin/env python3
"""随机抽样行 (sample-lines): 对大文件做 reservoir sampling 抽取 N 行或按比例抽样，
逐行流式处理，无需把整个文件载入内存。

用法:
  python -I sample-lines.py -n N [-s SEED] [FILE]
  python -I sample-lines.py -r RATIO [-s SEED] [FILE]

选项:
  -n, --count N   固定抽取 N 行（Vitter reservoir sampling，逐行扫描一遍）
  -r, --ratio R   按比例 R∈[0,1] 抽样（每行独立以概率 R 保留，保持原顺序）
  -s, --seed SEED 随机种子（可复现）
  FILE            输入文件；缺省或为 - 时读 stdin

-n 与 -r 必须二选一。结果输出到 stdout。

示例:
  python -I sample-lines.py -n 5 -s 42 big.log
  python -I sample-lines.py -r 0.1 -s 7 access.log
  cat big.log | python -I sample-lines.py -n 10
"""

import argparse
import random
import sys

# Windows 控制台/管道下强制 UTF-8，避免 Git Bash 管道输入输出乱码
for _s in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="流式随机抽样文本行（reservoir sampling / 比例抽样）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("-n", "--count", type=int, help="抽取的行数")
    g.add_argument("-r", "--ratio", type=float, help="抽样比例 0~1")
    ap.add_argument("-s", "--seed", type=int, default=None, help="随机种子")
    ap.add_argument("file", nargs="?", default="-", help="输入文件，缺省读 stdin")
    args = ap.parse_args()

    if args.count is not None and args.count < 0:
        ap.error("-n 不能为负")
    if args.ratio is not None and not (0.0 <= args.ratio <= 1.0):
        ap.error("-r 必须在 [0,1] 区间")

    if args.file == "-":
        stream = sys.stdin
    else:
        stream = open(args.file, "r", encoding="utf-8", errors="replace")

    rng = random.Random(args.seed)
    try:
        if args.count is not None:
            # Vitter Algorithm R: 水库容量 n，逐行替换，内存 O(n)
            n = args.count
            reservoir = []
            for i, line in enumerate(stream, 1):
                if len(reservoir) < n:
                    reservoir.append(line)
                else:
                    j = rng.randint(1, i)
                    if j <= n:
                        reservoir[j - 1] = line
            for line in reservoir:
                sys.stdout.write(line)
        else:
            for line in stream:
                if rng.random() < args.ratio:
                    sys.stdout.write(line)
    finally:
        if stream is not sys.stdin:
            stream.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
