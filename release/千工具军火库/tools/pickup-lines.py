#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""土味情话机（pickup-lines）。

用途：
    随机输出土味情话，支持 --subject 自定义主语（情话说给谁听）。

示例命令：
    python pickup-lines.py                      # 随机来一句
    python pickup-lines.py -n 3                 # 连来三句
    python pickup-lines.py -s 小美              # 对小美说
    python pickup-lines.py -s 老板 -n 2         # 对老板连说两句（后果自负）
    python pickup-lines.py --seed 7             # 固定随机种子，方便复现
"""

import argparse
import random
import sys

# 语料模板，{s} 会被替换成主语
LINES = [
    "你猜我的心脏在哪边？左边？错，在{s}那边。",
    "{s}，你知道你和星星的区别吗？星星在天上，{s}在我心里。",
    "最近有个谣言说我喜欢{s}，我必须澄清一下：那不是谣言。",
    "我不贪心，一生只有两个愿望：{s}在身边，{s}别走远。",
    "你会弹钢琴吗？不会？那{s}是怎么拨动我心弦的？",
    "我的择偶标准只有一条：像{s}这样的。",
    "{s}是不是近视？不然怎么没发现我眼里的喜欢。",
    "我发现{s}这个人有点怪——怪好看的。",
    "有件事我一直没说：我的余生规划里，每一页都写着{s}。",
    "你知道我为什么感冒了吗？因为我对{s}完全没抵抗力。",
    "{s}，你最近是不是胖了？在我心里的分量变重了。",
    "昨晚梦到{s}了，醒来都不想起，怕把好运气落在梦里。",
    "我数学不好，但我会算：我 + {s} = 一颗完整的心。",
    "苦海无涯，回头是{s}。",
    "想去{s}的城市吃火锅、看晚霞，顺便看{s}。",
    "人生建议：别对{s}心动——因为已经有人抢先了，那个人是我。",
    "你知道我的缺点是什么吗？缺点{s}。",
    "天冷了，我最想去的地方不是被窝，是{s}的心里。",
    "问：世上最美的风景在哪？答：{s}抬头的那个方向。",
    "{s}，你是不是学过魔法？不然我怎么一见到你就走不动路。",
]


def pick(pool, n):
    """从语料池取 n 条；数量不超过池子大小时尽量不重复。"""
    if n <= 0:
        return []
    if n <= len(pool):
        return random.sample(pool, n)
    out = list(pool)
    out.extend(random.choice(pool) for _ in range(n - len(pool)))
    return out


def main() -> int:
    try:  # Windows 控制台默认 GBK，切到 UTF-8 避免输出报错
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        prog="pickup-lines",
        description="土味情话机：随机输出土味情话，支持自定义主语。",
    )
    parser.add_argument("-s", "--subject", default="你", help="情话主语（默认：你）")
    parser.add_argument("-n", "--count", type=int, default=1, help="生成条数（默认 1）")
    parser.add_argument("--seed", type=int, default=None, help="随机种子（用于复现）")
    args = parser.parse_args()

    if args.count < 1:
        parser.error("-n/--count 必须 >= 1")
    if args.seed is not None:
        random.seed(args.seed)

    for line in pick(LINES, args.count):
        print(line.format(s=args.subject))
    return 0


if __name__ == "__main__":
    sys.exit(main())
