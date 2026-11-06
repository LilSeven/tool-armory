#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""猜拳陪练 —— 与电脑猜拳，实时累计战绩，连胜连败自动播报梗文案。

用法:
    python rock-paper-scissors.py               # 交互: 输入 石头/剪刀/布(或 r/p/s), q 结束
    printf '石头\n剪刀\n布\nq\n' | python rock-paper-scissors.py   # 管道喂招
    python rock-paper-scissors.py --auto 10     # 电脑左右互搏 10 局, 看战绩分布
    python rock-paper-scissors.py --seed 7      # 固定电脑出招的随机种子

玩法:
    每局输入 石头/rock/r、剪刀/scissors/s、布/paper/p;
    q/quit/exit/退出 结束并结算战绩; 输错会提示, 不计分。
    3 连胜/3 连败起触发梗播报, 结算面板含胜率与最长连胜。
"""

import argparse
import random
import sys

MOVES = ("石头", "剪刀", "布")
ALIASES = {
    "石头": "石头", "rock": "石头", "r": "石头", "锤子": "石头",
    "剪刀": "剪刀", "scissors": "剪刀", "s": "剪刀",
    "布": "布", "paper": "布", "p": "布", "包子": "布",
}
BEATS = {"石头": "剪刀", "剪刀": "布", "布": "石头"}

WIN_MEMES = {
    3: "三连胜! 手起刀落, 对面已经开始查你身份证了。",
    5: "五连胜! 建议直接报名世界猜拳锦标赛。",
    7: "七连胜! 电脑已提交工单申请更换对手。",
}
WIN_MEME_MAX = "胜负已无悬念, 电脑连夜删库跑路。"
LOSE_MEMES = {
    3: "三连败……先别砸键盘, 深呼吸再来。",
    5: "五连败, 你这只手怕不是对方的卧底。",
    7: "七连败, 建议换只手, 或换个宇宙。",
}
LOSE_MEME_MAX = "电脑表示赢麻了, 主动申请让你一局。"


def setup_stdio():
    """统一输入输出编码, 避免中文在管道/重定向时乱码。"""
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def judge(user, cpu):
    if user == cpu:
        return "平"
    return "胜" if BEATS[user] == cpu else "负"


def streak_meme(result, streak):
    if result == "胜" and streak >= 3:
        return WIN_MEMES.get(streak, WIN_MEME_MAX)
    if result == "负" and streak >= 3:
        return LOSE_MEMES.get(streak, LOSE_MEME_MAX)
    return ""


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="猜拳陪练: 与电脑猜拳, 累计战绩并播报连胜梗文案。")
    parser.add_argument("--auto", type=int, default=0, metavar="N",
                        help="自动对弈 N 局 (电脑左右互搏), 不读键盘")
    parser.add_argument("--seed", type=int, default=None, help="随机种子, 复现结果用")
    args = parser.parse_args(argv)
    if args.auto < 0:
        parser.error("--auto 局数不能为负")
    rng = random.Random(args.seed)

    stats = {"胜": 0, "负": 0, "平": 0}
    win_streak = lose_streak = best_streak = 0
    round_no = 0
    eof_note = ""

    def one_round(user):
        nonlocal round_no, win_streak, lose_streak, best_streak
        cpu = rng.choice(MOVES)
        result = judge(user, cpu)
        round_no += 1
        stats[result] += 1
        if result == "胜":
            win_streak += 1
            lose_streak = 0
            best_streak = max(best_streak, win_streak)
        elif result == "负":
            lose_streak += 1
            win_streak = 0
        else:
            win_streak = 0
            lose_streak = 0
        meme = streak_meme(result, win_streak if result == "胜" else lose_streak)
        line = "第{}局: 你出 {}, 电脑出 {}, 你: {}".format(round_no, user, cpu, result)
        if meme:
            line += "  【梗播报】" + meme
        print(line)

    if args.auto > 0:
        print("自动对弈 {} 局, 电脑左右互搏:".format(args.auto))
        for _ in range(args.auto):
            one_round(rng.choice(MOVES))
    else:
        print("猜拳陪练就位! 出招: 石头/剪刀/布 (可简写 r/p/s), q 结束并结算。")
        while True:
            try:
                raw = input("出招> ").strip().lower()
            except EOFError:
                eof_note = "(输入见底, 提前收摊)"
                break
            if not raw:
                continue
            if raw in ("q", "quit", "exit", "退出"):
                break
            if raw in ALIASES:
                one_round(ALIASES[raw])
            else:
                print("看不懂 {!r}, 只认: 石头/剪刀/布 或 r/p/s, q 结束。".format(raw))

    if round_no == 0:
        print("一局未战, 战绩清白, 下次再来。")
        return 0
    rate = stats["胜"] * 100.0 / round_no
    print("========== 战绩总览 ==========")
    print("共 {} 局: 胜 {} / 负 {} / 平 {}".format(
        round_no, stats["胜"], stats["负"], stats["平"]))
    print("最长连胜: {} 局".format(best_streak))
    print("胜率 {:.1f}%".format(rate))
    if eof_note:
        print(eof_note)
    return 0


if __name__ == "__main__":
    setup_stdio()
    sys.exit(main())
