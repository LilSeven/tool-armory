#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""是非神谕 —— 只回答 是 / 否 / 再问一次，并附赠一条随机胡扯的理由。

用法:
    python yes-no-oracle.py "该不该跳槽"
    python yes-no-oracle.py --seed 7 "明天要不要早起"
    python yes-no-oracle.py            # 一问一答模式: 每行一个问题, 空行结束

规矩:
    答案三选一: 是(40%) / 否(40%) / 再问一次(20%);
    理由全部由神谕现场胡扯, 一本正经, 概不负责。
"""

import argparse
import random
import sys

VERDICTS = ("是", "否", "再问一次")
WEIGHTS = (2, 2, 1)

REASONS = {
    "是": [
        "水星刚结束逆行, 万事皆宜, 尤其宜答应你。",
        "茶杯里的茶叶梗根根直立, 像在点头。",
        "今晨第一声鸟叫是三连音, 按《胡扯占卜学》第三章, 此乃大吉。",
        "宇宙后台刚把你的问题标记为已读, 并顺手点了同意。",
        "你的问题笔画数与今日幸运数只差一个质数, 吉。",
        "神谕掷了三枚铜钱, 三枚齐刷刷立正——想都说不出个不字。",
    ],
    "否": [
        "水星正在逆行, 而它最近心情不太好。",
        "你问题里的问号是全角的, 能量太重, 神谕扛不动。",
        "今夜月亮缺了一角, 诸事不宜, 尤其不宜答应你。",
        "神谕掷了三枚铜钱, 两枚躺平一枚逃跑——此乃否之象。",
        "你的问题让神谕想起了前任, 它现在不想说话。",
        "今日宜静不宜动, 神谕建议把这事压到下一个满月。",
    ],
    "再问一次": [
        "你的问题被一阵妖风吹进云里, 神谕表示看不清, 重问一遍。",
        "此刻神谕正在充电, 电量只剩百分之三, 稍后再问。",
        "信号不好, 神谕那边全是雪花屏, 请重新提问。",
        "你问得太急, 把答案吓跑了, 深呼吸后再问一次。",
        "这道题需要先摇三下神谕球, 你一下都没摇, 重问。",
        "神谕刚才打了个喷嚏, 没听清, 再说一遍。",
    ],
}


def setup_stdio():
    """统一输入输出编码, 避免中文在管道/重定向时乱码。"""
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def answer_once(rng, question):
    verdict = rng.choices(VERDICTS, weights=WEIGHTS)[0]
    reason = rng.choice(REASONS[verdict])
    print("[是非神谕]")
    print("问: {}".format(question))
    print("答: {}".format(verdict))
    print("理由: {}".format(reason))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="是非神谕: 只回答 是/否/再问一次, 并附一条随机胡扯理由。")
    parser.add_argument("question", nargs="*", help="要问的是非题 (缺省则进入一问一答模式)")
    parser.add_argument("--seed", type=int, default=None, help="随机种子, 复现结果用")
    args = parser.parse_args(argv)
    rng = random.Random(args.seed)

    if args.question:
        question = " ".join(args.question).strip()
        if question:
            answer_once(rng, question)
            return 0

    print("是非神谕已就位, 每行抛来一个是非题, 空行结束。")
    try:
        while True:
            try:
                line = input("问:> ").strip()
            except EOFError:
                break
            if not line:
                break
            answer_once(rng, line)
    except KeyboardInterrupt:
        pass
    print("神谕闭麦, 下次再问。")
    return 0


if __name__ == "__main__":
    setup_stdio()
    sys.exit(main())
