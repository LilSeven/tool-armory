#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""莎翁骂人词典（shakespeare-insult）。

用途：
    用莎士比亚 insult kit 的三栏词库（形容词 + 形容词 + 名词）
    随机组合出莎翁风格的骂人短句，例如：
        Thou pribbling knotty-pated moldwarp!
    支持 -t 点名开骂。

示例命令：
    python shakespeare-insult.py                # 随机来一句
    python shakespeare-insult.py -n 3           # 连来三句
    python shakespeare-insult.py -t 张三        # 点名开骂
    python shakespeare-insult.py --list-cols    # 查看三栏词库规模
    python shakespeare-insult.py --seed 7       # 固定随机种子，方便复现
"""

import argparse
import random
import sys

# 第一栏：形容词
COL1 = [
    "artless", "bawdy", "beslubbering", "bootless", "churlish", "cockered",
    "clouted", "craven", "currish", "droning", "errant", "fawning",
    "fobbing", "froward", "frothy", "gleeking", "goatish", "gorbellied",
    "impertinent", "infectious", "jarring", "loggerheaded", "lumpish",
    "mammering", "mangled", "mewling", "paunchy", "pribbling", "puking",
    "puny", "quailing", "rank", "reeky", "roguish", "ruttish", "saucy",
    "spleeny", "spongy", "surly", "tottering", "unmuzzled", "vain",
    "venomed", "villainous", "warped", "wayward", "weedy", "yeasty",
]

# 第二栏：复合形容词
COL2 = [
    "base-court", "bat-fowling", "beetle-headed", "boil-brained",
    "clapper-clawed", "clay-brained", "common-kissing", "crook-pated",
    "dismal-dreaming", "dizzy-eyed", "doghearted", "dread-bolted",
    "earth-vexing", "elf-skinned", "fat-kidneyed", "fen-sucked",
    "flap-mouthed", "fly-bitten", "folly-fallen", "foot-licking",
    "foul-mouthed", "full-gorged", "guts-griping", "half-faced",
    "hasty-witted", "hedge-born", "hell-hated", "idle-headed",
    "ill-breeding", "ill-nurtured", "knotty-pated", "milk-livered",
    "motley-minded", "onion-eyed", "plume-plucked", "pottle-deep",
    "pox-marked", "reeling-ripe", "rough-hewn", "rude-growing",
    "rump-fed", "shard-borne", "sheep-biting", "spur-galled",
    "swag-bellied", "tardy-gaited", "tickle-brained", "toad-spotted",
    "unchin-snouted", "weather-bitten",
]

# 第三栏：名词
COL3 = [
    "apple-john", "baggage", "barnacle", "bladder", "boar-pig", "bugbear",
    "bum-bailey", "canker-blossom", "clack-dish", "clotpole", "coxcomb",
    "codpiece", "death-token", "dewberry", "flap-dragon", "flax-wench",
    "flirt-gill", "foot-licker", "fustilarian", "giglet", "gudgeon",
    "haggard", "harpy", "hedge-pig", "horn-beast", "jolthead", "leech",
    "lout", "maggot-pie", "malt-worm", "mammet", "mewler", "minnow",
    "miscreant", "moldwarp", "mumble-news", "nut-hook", "pigeon-egg",
    "pignut", "pumpion", "puttock", "ratsbane", "scut", "skainsmate",
    "strumpet", "varlot", "vassal", "whey-face", "wittol", "yeasty-wort",
]


def insult() -> str:
    """三栏各随机取一词，组合成莎翁式骂人短句。"""
    return "Thou {a} {b} {c}!".format(
        a=random.choice(COL1), b=random.choice(COL2), c=random.choice(COL3)
    )


def main() -> int:
    try:  # Windows 控制台默认 GBK，切到 UTF-8 避免输出报错
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        prog="shakespeare-insult",
        description="莎翁骂人词典：三栏词库组合出莎士比亚风格的骂人短句。",
    )
    parser.add_argument("-t", "--target", default=None, help="点名对象，如：-t 张三")
    parser.add_argument("-n", "--count", type=int, default=1, help="生成条数（默认 1）")
    parser.add_argument("--list-cols", action="store_true", help="列出三栏词库规模后退出")
    parser.add_argument("--seed", type=int, default=None, help="随机种子（用于复现）")
    args = parser.parse_args()

    if args.list_cols:
        print("第一栏（形容词）{} 词；第二栏（复合形容词）{} 词；第三栏（名词）{} 词".format(
            len(COL1), len(COL2), len(COL3)))
        print("可组合出 {} 种不同骂法。".format(len(COL1) * len(COL2) * len(COL3)))
        return 0
    if args.count < 1:
        parser.error("-n/--count 必须 >= 1")
    if args.seed is not None:
        random.seed(args.seed)

    for _ in range(args.count):
        line = insult()
        if args.target:
            line = "{t}！{line}".format(t=args.target, line=line)
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
