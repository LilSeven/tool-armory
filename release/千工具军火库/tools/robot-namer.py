#!/usr/bin/env python3
"""机器人编号名 —— RX-78 / MK-IV 风格机甲编号, 外加昵称与小传。

用途:
    生成「编号 + 昵称 + 型号 + 武装 + 小传」的虚构机甲档案,
    可用于写作、跑团、起网名。

用法:
    python robot-namer.py [--series SER] [--count N] [--seed SEED]

示例命令:
    python robot-namer.py                       # 随机出 3 台机甲
    python robot-namer.py --series RX --count 2
    python robot-namer.py --series MK --seed 1

编号规则: 普通系列为 "前缀-两位数字(可带改型后缀)", MK 系列为 "MK-罗马数字"。
内置前缀: RX MS ZG GN OZ AS VK LM NR MBF YMS RMS MK (也接受自定义 1-5 位字母)
仅依赖 Python 标准库; 成功时退出码为 0。
"""

from __future__ import annotations

import argparse
import random
import re
import sys

SERIES = ["RX", "MS", "ZG", "GN", "OZ", "AS", "VK", "LM", "NR", "MBF", "YMS", "RMS", "MK"]

NICKNAMES = ["红色彗星", "白狼", "夜枭", "苍蓝闪电", "钢铁玫瑰", "孤狼", "雷霆",
             "幽灵", "曙光", "破晓", "沉默山丘", "白骑士", "黑曜石", "星尘",
             "暴风眼", "零式", "不冻港", "铜豌豆"]

TYPE = ["试作", "量产", "改修", "特装", "次世代"]
ROLE = ["侦察机", "狙击机", "近接突击机", "重装炮击机", "护航机", "训练机"]
WEAPONS = ["光束军刀", "头部火神炮", "肩部导弹舱", "高能粒子炮", "高频振动刀",
           "电磁步枪", "盾牌撞角", "浮游炮", "轨道狙击步枪", "霰弹喷射手炮"]
BIO = ["单机守住过轨道电梯", "在暴雨里击落三台王牌机", "失踪于木星航线, 十年后自己开了回来",
       "驾驶舱里只贴一张全家福", "涂装被粉丝做成应援色", "曾被误认成 UFO 登上新闻",
       "停产那天全基地鸣笛三分钟", "出勤记录一片空白, 战果栏全是问号"]

_ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
          (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def to_roman(n: int) -> str:
    out = []
    for v, s in _ROMAN:
        while n >= v:
            out.append(s)
            n -= v
    return "".join(out)


def gen_code(rng: random.Random, series: str) -> str:
    if series == "MK":
        return "MK-%s" % to_roman(rng.randint(1, 12))
    num = rng.randint(1, 99)
    tail = rng.choice(["", "", "", "-2", "-A", "-B", "改", "-%s" % to_roman(rng.randint(2, 6))])
    return "%s-%02d%s" % (series, num, tail)


def gen_robot(rng: random.Random, series: str, used_nicks: set) -> dict:
    code = gen_code(rng, series)
    w1, w2 = rng.sample(WEAPONS, 2)
    nick = rng.choice(NICKNAMES)
    for _ in range(20):
        if nick not in used_nicks:
            break
        nick = rng.choice(NICKNAMES)
    return {
        "code": code,
        "nick": nick,
        "type": "%s型%s" % (rng.choice(TYPE), rng.choice(ROLE)),
        "weapons": "%s / %s" % (w1, w2),
        "year": rng.randint(79, 255),
        "bio": rng.choice(BIO),
    }


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    parser = argparse.ArgumentParser(
        description="机器人编号名: RX-78 / MK-IV 风格机甲编号 + 昵称")
    parser.add_argument("--series", default=None,
                        help="指定编号前缀, 如 RX / MS / MK; 缺省随机")
    parser.add_argument("--count", type=int, default=3, help="生成数量 (默认 3)")
    parser.add_argument("--seed", type=int, default=None, help="随机种子, 便于复现")
    args = parser.parse_args(argv)

    if args.count < 1:
        parser.error("--count 至少为 1")
    series = None
    if args.series is not None:
        series = args.series.upper()
        if not re.fullmatch(r"[A-Z]{1,5}", series):
            parser.error("编号前缀应为 1-5 个英文字母, 如 RX / MS / MK")

    rng = random.Random(args.seed)
    seen = set()
    used_nicks = set()
    shown = 0
    attempts = 0
    while shown < args.count and attempts < args.count * 200:
        attempts += 1
        ser = series or rng.choice(SERIES)
        bot = gen_robot(rng, ser, used_nicks)
        if bot["code"] in seen:
            continue
        seen.add(bot["code"])
        used_nicks.add(bot["nick"])
        shown += 1
        print("%d. %s 「%s」" % (shown, bot["code"], bot["nick"]))
        print("   型号: %s" % bot["type"])
        print("   武装: %s" % bot["weapons"])
        print("   小传: %04d 年出厂, %s" % (bot["year"], bot["bio"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
