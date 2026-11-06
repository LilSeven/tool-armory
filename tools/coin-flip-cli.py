#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""硬币决策器 —— 抛硬币二选一, 支持 -n 连抛并统计正反面比例。

用途:
    犹豫不决时抛一次硬币拿主意; 加 -n 连抛 N 次并输出正/反面次数与比例;
    可用 --heads/--tails 自定义两面对应的选项, 直接给出决策结果。

示例:
    python coin-flip-cli.py                                   # 抛一次
    python coin-flip-cli.py -n 10                             # 连抛 10 次并统计
    python coin-flip-cli.py --heads 吃火锅 --tails 吃烧烤      # 二选一决策
    python coin-flip-cli.py -n 100 -q                         # 只看统计不列明细

退出码: 0 成功; 2 参数错误。
"""

import argparse
import random
import sys

DEFAULT_HEADS = "正面"
DEFAULT_TAILS = "反面"
MAX_COUNT = 1000000


def _setup_stdio():
    """Windows 下把标准输出/错误切到 UTF-8, 避免中文在管道/重定向中乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def count_type(value):
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("次数须为整数: {!r}".format(value))
    if not 1 <= n <= MAX_COUNT:
        raise argparse.ArgumentTypeError("次数须在 1~{} 之间".format(MAX_COUNT))
    return n


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="coin-flip-cli",
        description="抛硬币二选一; -n 连抛 N 次并统计正反面比例。")
    parser.add_argument("-n", "--count", type=count_type, default=1, metavar="N",
                        help="连抛次数 (默认 1, 上限 {})".format(MAX_COUNT))
    parser.add_argument("--heads", default=DEFAULT_HEADS,
                        help="正面标签 (默认: 正面)")
    parser.add_argument("--tails", default=DEFAULT_TAILS,
                        help="反面标签 (默认: 反面)")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="只输出统计, 不逐次列出")
    args = parser.parse_args(argv)

    flips = [random.getrandbits(1) for _ in range(args.count)]  # 1=正面, 0=反面
    heads = sum(flips)
    tails = args.count - heads
    custom = (args.heads != DEFAULT_HEADS) or (args.tails != DEFAULT_TAILS)

    if args.count == 1:
        label = args.heads if flips[0] else args.tails
        if custom:
            print("抛硬币结果: {} (实际是{})".format(
                label, DEFAULT_HEADS if flips[0] else DEFAULT_TAILS))
        else:
            print("抛硬币结果: {}".format(label))
        return 0

    if not args.quiet:
        for i, flip in enumerate(flips, 1):
            print("第 {:>4} 次: {}".format(i, args.heads if flip else args.tails))
    rate = heads * 100.0 / args.count
    print("统计: 共抛 {} 次 | {} {} 次 ({:.1f}%) | {} {} 次 ({:.1f}%)".format(
        args.count, args.heads, heads, rate,
        args.tails, tails, 100.0 - rate))
    return 0


if __name__ == "__main__":
    _setup_stdio()
    sys.exit(main())
