#!/usr/bin/env python3
"""拼手气红包（red-envelope）——把指定金额随机拆成 N 份，并公布手气排行榜。

用途：发群红包前先彩排手气、活动抽奖演示、讲解随机分配算法。

示例命令：
  python red-envelope.py 8.88 -n 3               # 把 8.88 元随机拆成 3 份
  python red-envelope.py 100 -n 5 --seed 42      # 固定随机种子，结果可复现
  python red-envelope.py 66.6 -n 8 --sender 老王  # 带发红包人署名

算法：微信同款「二倍均值法」——以「分」为单位，每份在 [0.01, 剩余均值×2] 元内
随机，保证每份 ≥ 0.01 元且各份之和与总额精确相等（全程整数运算，无浮点误差）。
金额支持最多两位小数（元）。
退出码：0 成功；2 参数错误（金额非法、份数超过可拆金额等）；3 内部校验失败。
仅依赖 Python 标准库。
"""

from __future__ import annotations

import argparse
import random
import sys
from decimal import Decimal, InvalidOperation


def _utf8_stdio() -> None:
    """Windows 控制台/管道下强制 UTF-8 输出，避免中文乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _yuan(cents: int) -> str:
    """分 -> 元字符串（两位小数），全程整数运算。"""
    return f"{cents // 100}.{cents % 100:02d}"


def _split(total_cents: int, n: int, rng: random.Random) -> list[int]:
    """二倍均值法拆红包：每份至少 1 分，总和恰为 total_cents。"""
    shares: list[int] = []
    remain = total_cents
    for k in range(n, 1, -1):  # 还剩 k 份未拆
        hi = min(2 * remain // k, remain - (k - 1))  # 给后面每份至少留 1 分
        amt = rng.randint(1, hi)
        shares.append(amt)
        remain -= amt
    shares.append(remain)
    return shares


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="red-envelope",
        description="把指定金额随机拆成 N 份拼手气红包，并公布手气排行榜。",
    )
    parser.add_argument("amount", help="总金额（元，最多两位小数），如 8.88")
    parser.add_argument("-n", "--count", type=int, default=3,
                        help="拆成几份（默认 3）")
    parser.add_argument("--sender", default="", help="发红包人署名（可选）")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子（相同种子结果可复现）")
    args = parser.parse_args(argv)

    if args.count < 1:
        print("错误：份数 -n 必须 ≥ 1。", file=sys.stderr)
        return 2
    try:
        amt = Decimal(args.amount)
    except InvalidOperation:
        print(f"错误：金额 {args.amount!r} 不是合法数字。", file=sys.stderr)
        return 2
    if amt <= 0:
        print("错误：金额必须大于 0。", file=sys.stderr)
        return 2
    cents_dec = amt * 100
    if cents_dec != cents_dec.to_integral_value():
        print("错误：金额最多支持两位小数。", file=sys.stderr)
        return 2
    total = int(cents_dec)
    if total < args.count:
        print(f"错误：{args.amount} 元拆不成 {args.count} 份，每份至少 0.01 元。",
              file=sys.stderr)
        return 2

    shares = _split(total, args.count, random.Random(args.seed))
    if sum(shares) != total or min(shares) < 1:  # 内置自检：总额精确、无 0 份
        print("内部错误：拆分校验失败。", file=sys.stderr)
        return 3

    who = f"{args.sender} " if args.sender else ""
    seed_text = f"（随机种子 {args.seed}）" if args.seed is not None else ""
    bar = "-" * 38
    print(f"{who}发出拼手气红包：{_yuan(total)} 元 × {args.count} 份{seed_text}")
    print(bar)
    for i, c in enumerate(shares, 1):
        print(f"第 {i} 份   {_yuan(c)} 元")
    print(bar)

    order = sorted(range(args.count), key=lambda i: shares[i], reverse=True)
    print("手气排行榜：")
    for rank, i in enumerate(order, 1):
        mark = ""
        if args.count >= 2 and rank == 1:
            mark = "  ← 手气王"
        elif args.count >= 2 and rank == args.count:
            mark = "  ← 手气最差"
        print(f"  {rank}. {_yuan(shares[i])} 元（第 {i + 1} 份）{mark}")
    print(f"合计 {_yuan(total)} 元，已精确拆成 {args.count} 份，无分差。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
