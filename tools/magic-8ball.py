#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""神奇预言球 —— 问一个是非问题，从 20 条经典 Magic 8-Ball 神谕中随机抽出一条回答你。

用法:
    python magic-8ball.py "我今年会发财吗"
    python magic-8ball.py 明天 该不该请假        # 多个参数会自动拼成一句话
    python magic-8ball.py --seed 42 "考试能过吗"  # 固定种子, 复现神谕
    python magic-8ball.py                        # 不带问题则现场追问一句

神谕出处:
    沿用 1946 年问世的 Magic 8-Ball 的 20 条标准答案:
    10 条肯定 / 5 条暧昧 / 5 条否定, 中英对照输出。
    神谕仅供娱乐, 人生大事请自己拿主意。
"""

import argparse
import random
import sys

ANSWERS = [
    ("肯定的", "It is certain"),
    ("必然如此", "It is decidedly so"),
    ("毫无疑问", "Without a doubt"),
    ("当然, 肯定", "Yes, definitely"),
    ("尽管放心", "You may rely on it"),
    ("依我看, 行", "As I see it, yes"),
    ("大概率能成", "Most likely"),
    ("前景光明", "Outlook good"),
    ("是", "Yes"),
    ("各种迹象都指向是", "Signs point to yes"),
    ("回答模糊, 再试一次", "Reply hazy, try again"),
    ("稍后再问", "Ask again later"),
    ("现在还是别告诉你的好", "Better not tell you now"),
    ("现在无法预测", "Cannot predict now"),
    ("集中精神, 再问一遍", "Concentrate and ask again"),
    ("别抱太大希望", "Don't count on it"),
    ("我的回答是否", "My reply is no"),
    ("我的线人说不行", "My sources say no"),
    ("前景不太妙", "Outlook not so good"),
    ("悬", "Very doubtful"),
]


def setup_stdio():
    """统一输入输出编码, 避免中文在管道/重定向时乱码。"""
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="神奇预言球: 问一个是非问题, 从 20 条经典神谕里随机给答案。")
    parser.add_argument("question", nargs="*", help="你的问题 (缺省则现场追问)")
    parser.add_argument("--seed", type=int, default=None, help="随机种子, 复现神谕用")
    args = parser.parse_args(argv)

    question = " ".join(args.question).strip()
    if not question:
        try:
            question = input("球已就位, 请问:> ").strip()
        except EOFError:
            parser.error('没有收到问题: 给我一个疑问句, 例如 "我今年会发财吗"')
    if not question:
        parser.error('问题是空的: 给我一个疑问句, 例如 "我今年会发财吗"')

    rng = random.Random(args.seed)
    zh, en = rng.choice(ANSWERS)
    print("[神奇预言球]")
    print("你的问题: {}".format(question))
    print("摇一摇…… 神谕曰: 【{}】 ({})".format(zh, en))
    print("(神谕仅供娱乐, 概不负责)")
    return 0


if __name__ == "__main__":
    setup_stdio()
    sys.exit(main())
