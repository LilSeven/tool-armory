#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""彩虹屁生成器（rainbow-fart）。

用途：
    随机生成夸人语句（彩虹屁），支持 --target 指定夸奖对象，
    让每一发彩虹屁都精准命中目标。

示例命令：
    python rainbow-fart.py                      # 随机夸一句
    python rainbow-fart.py -n 3                 # 连夸三句
    python rainbow-fart.py -t 老板              # 专门夸老板
    python rainbow-fart.py -t 老板 -n 2         # 连夸老板两句
    python rainbow-fart.py --seed 7             # 固定随机种子，方便复现
"""

import argparse
import random
import sys

# 语料模板，{t} 会被替换成夸奖对象
TEMPLATES = [
    "{t}，你身上有光，我抓不住，但它照亮了整个工位。",
    "认识{t}之后，我终于明白「优秀」这个词为什么存在——它在等{t}。",
    "{t}一开口，连Wi-Fi信号都满了两格。",
    "如果努力有形状，那一定是{t}认真做事的侧脸。",
    "别人是行走的荷尔蒙，{t}是行走的多巴胺，看一眼就开心。",
    "老天爷捏人的时候肯定给{t}多加了一勺才华，还不小心洒了半勺魅力。",
    "{t}啊{t}，你这么厉害，让旁边人的努力情何以堪。",
    "由衷建议：{t}这样的存在应该申报非物质文化遗产。",
    "{t}的脑回路是人类文明的高速公路，又宽又畅通。",
    "每次和{t}聊天，都像给灵魂做了一次SPA。",
    "{t}，你的存在本身，就是对「靠谱」二字最好的注释。",
    "科学家说人体七成是水，{t}的七成一定是才华。",
    "{t}做事的效率，让我怀疑你把一天过成了四十八小时。",
    "遇见{t}之前，我以为世上没有完美的人；现在我错了，但错得很开心。",
    "{t}的笑容是可再生资源，取之不尽，用之不竭，还零污染。",
    "如果说人生是开卷考试，那{t}一定是标准答案本人。",
    "{t}说话的分量，比电梯超载警告还有说服力。",
    "别人发光是反光，{t}发光是自燃，还自带氧气的那种。",
    "{t}的审美、情商和实力是三条平行线——每一条都已经拉满了。",
    "夸{t}这件事，我愿意加班，不要加班费。",
    "把{t}放进人群，聚光灯会自动找上门，连美颜相机都可以歇了。",
    "{t}的耐心像大海，实力像高山，脾气好得像不排队的大商场。",
    "我怀疑{t}上辈子拯救了银河系，不然这辈子怎么这么顶。",
    "别问{t}为什么这么优秀，问就是天赋，再问还是天赋。",
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
        prog="rainbow-fart",
        description="彩虹屁生成器：随机生成夸人语句，可指定夸奖对象。",
    )
    parser.add_argument("-t", "--target", default="你", help="夸奖对象（默认：你）")
    parser.add_argument("-n", "--count", type=int, default=1, help="生成条数（默认 1）")
    parser.add_argument("--seed", type=int, default=None, help="随机种子（用于复现）")
    args = parser.parse_args()

    if args.count < 1:
        parser.error("-n/--count 必须 >= 1")
    if args.seed is not None:
        random.seed(args.seed)

    for line in pick(TEMPLATES, args.count):
        print(line.format(t=args.target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
