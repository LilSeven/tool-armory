#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""幸运号码机 —— 模拟双色球/大乐透摇号，可锁定已选号、只重摇其余位置。

用法:
    python lucky-numbers.py                            # 随机来一注双色球(默认)
    python lucky-numbers.py --game dlt                 # 来一注大乐透
    python lucky-numbers.py -n 5                       # 连摇 5 注
    python lucky-numbers.py --lock "3,17,22"           # 锁定红球 3/17/22, 其余重摇
    python lucky-numbers.py --lock "3,17" --lock2 "8"  # 同时锁定蓝球 8
    python lucky-numbers.py --game dlt --lock "5,12" --lock2 "9,11"

规则:
    双色球 ssq: 红球 6 个 (1-33, 不重复) + 蓝球 1 个 (1-16)
    大乐透 dlt: 前区 5 个 (1-35, 不重复) + 后区 2 个 (1-12)
    --lock  锁定前区/红球号码, 逗号分隔
    --lock2 锁定蓝球/后区号码, 逗号分隔
    锁定号保持不动, 其余位置重新随机。

纯属娱乐, 不构成任何购彩建议。
"""

import argparse
import random
import sys

GAMES = {
    "ssq": {"main_n": 6, "main_hi": 33, "extra_n": 1, "extra_hi": 16,
            "main_name": "红球", "extra_name": "蓝球", "title": "双色球"},
    "dlt": {"main_n": 5, "main_hi": 35, "extra_n": 2, "extra_hi": 12,
            "main_name": "前区", "extra_name": "后区", "title": "大乐透"},
}


def setup_stdio():
    """统一输入输出编码, 避免中文在管道/重定向时乱码。"""
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def parse_locked(text, lo, hi, label):
    """把 "3,17,22" 解析成号码列表, 校验范围与重复。"""
    nums = []
    for part in text.replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            n = int(part)
        except ValueError:
            raise SystemExit("[错误] {}里的 {!r} 不是整数".format(label, part))
        if not lo <= n <= hi:
            raise SystemExit("[错误] {}号码 {} 超出范围 {}-{}".format(label, n, lo, hi))
        if n in nums:
            raise SystemExit("[错误] {}号码 {} 重复了".format(label, n))
        nums.append(n)
    return nums


def fill(rng, locked, count, hi):
    """在 1..hi 中补齐号码到 count 个; locked 原样保留, 补摇的不会与它重复。"""
    if len(locked) > count:
        raise SystemExit("[错误] 锁定了 {} 个号码, 超过该区需要的 {} 个"
                         .format(len(locked), count))
    pool = [x for x in range(1, hi + 1) if x not in locked]
    return sorted(locked + rng.sample(pool, count - len(locked)))


def fmt(nums):
    return " ".join("{:02d}".format(n) for n in nums)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="幸运号码机: 模拟双色球/大乐透摇号, 支持锁定已选号重摇其余。")
    parser.add_argument("--game", choices=sorted(GAMES), default="ssq",
                        help="玩法: ssq=双色球(默认), dlt=大乐透")
    parser.add_argument("-n", "--count", type=int, default=1, help="生成注数 (默认 1)")
    parser.add_argument("--lock", default="", metavar="号,号",
                        help='锁定前区/红球号码, 逗号分隔, 如 "3,17,22"')
    parser.add_argument("--lock2", default="", metavar="号,号",
                        help="锁定蓝球/后区号码, 逗号分隔")
    parser.add_argument("--seed", type=int, default=None, help="随机种子, 复现结果用")
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("-n 注数至少为 1")

    spec = GAMES[args.game]
    locked_main = parse_locked(args.lock, 1, spec["main_hi"], spec["main_name"])
    locked_extra = parse_locked(args.lock2, 1, spec["extra_hi"], spec["extra_name"])
    if len(locked_main) > spec["main_n"]:
        parser.error("{}最多锁定 {} 个".format(spec["main_name"], spec["main_n"]))
    if len(locked_extra) > spec["extra_n"]:
        parser.error("{}最多锁定 {} 个".format(spec["extra_name"], spec["extra_n"]))

    rng = random.Random(args.seed)
    tag = " (含锁定号)" if (locked_main or locked_extra) else ""
    for i in range(1, args.count + 1):
        main_balls = fill(rng, locked_main, spec["main_n"], spec["main_hi"])
        extra_balls = fill(rng, locked_extra, spec["extra_n"], spec["extra_hi"])
        print("{} 第{:02d}注: {} {} + {} {}".format(
            spec["title"], i, spec["main_name"], fmt(main_balls),
            spec["extra_name"], fmt(extra_balls)) + tag)
    return 0


if __name__ == "__main__":
    setup_stdio()
    sys.exit(main())
