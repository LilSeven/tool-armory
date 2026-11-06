#!/usr/bin/env python3
"""random-mission.py — 今日任务签: 抽一枚每日挑战小签(单文件, 仅标准库)。

用途:
    从内置任务库(善意/学习/健康/探索/社交/整理 六类共 60 枚)中抽一枚"每日挑战签",
    输出签号、吉位(大吉/中吉/小吉)、类别与签文。默认按日期派生种子——同一天、
    同样参数重复抽取得到同一签, 适合当"今日份"任务; --fresh 则完全随机。

示例:
    python random-mission.py draw                     # 今日签(按日期固定)
    python random-mission.py draw --fresh             # 完全随机抽一签
    python random-mission.py draw --date 2026-11-03   # 抽指定日期的签
    python random-mission.py draw -c 善意 --fresh     # 只在"善意"类里抽
    python random-mission.py draw --count 3 --fresh   # 连抽 3 枚(不重复)
    python random-mission.py list                     # 列出全部任务签
    python random-mission.py list -c 健康             # 只列某一类
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
from datetime import date

MISSIONS = [
    ("善意", "今天夸一个同事, 说得具体。"),
    ("善意", "给一位很久没联系的朋友发句问候。"),
    ("善意", "帮身边的人做一件他没开口的小事。"),
    ("善意", "今天对服务员说三次谢谢。"),
    ("善意", "请同事喝一杯咖啡或奶茶。"),
    ("善意", "写一句感谢的话发给帮过你的人。"),
    ("善意", "给家里打个电话, 只聊五分钟闲话。"),
    ("善意", "把好位置让给需要的人。"),
    ("善意", "认真听一个人把话说完, 不打断。"),
    ("善意", "在群里真诚回应一条没人理的消息。"),
    ("学习", "学一个今天第一次听说的词或概念。"),
    ("学习", "读一篇和本职无关的短文。"),
    ("学习", "把昨天学到的东西讲给自己听一遍。"),
    ("学习", "把收藏夹里存了很久的一篇文章读完。"),
    ("学习", "花 15 分钟学一个顺手的小技巧。"),
    ("学习", "向一位懂行的人请教一个问题。"),
    ("学习", "记下今天遇到的一个好问题, 明天去查。"),
    ("学习", "教别人一招你熟而他不会的东西。"),
    ("学习", "速读一章书, 只求抓住一个观点。"),
    ("学习", "听一期播客或讲座的前十分钟。"),
    ("健康", "今天多喝一杯水, 少喝一杯含糖饮料。"),
    ("健康", "午饭后散步十分钟。"),
    ("健康", "睡前把手机放远一点。"),
    ("健康", "做十个深蹲, 分三次做完也行。"),
    ("健康", "今天 23 点前上床。"),
    ("健康", "拉伸肩颈三分钟。"),
    ("健康", "吃一份绿色蔬菜。"),
    ("健康", "爬两层楼梯代替电梯。"),
    ("健康", "用鼻子做十次慢而深的呼吸。"),
    ("健康", "今晚比昨天早睡十五分钟。"),
    ("探索", "上下班换一条没走过的路。"),
    ("探索", "尝试一家没吃过的店或一道没点过的菜。"),
    ("探索", "拍一张今天最有趣的照片。"),
    ("探索", "听一张从没听过的专辑的第一首歌。"),
    ("探索", "查一个一直好奇但没查过的问题。"),
    ("探索", "去一个从没去过的公园或街区走走。"),
    ("探索", "换个顺序做一件日常小事, 比如左手刷牙。"),
    ("探索", "看五分钟一个完全陌生领域的视频。"),
    ("探索", "在地图上随机挑个近处地标, 查查它的来历。"),
    ("探索", "给明天的自己留一个新点子。"),
    ("社交", "主动约一次午饭搭子。"),
    ("社交", "在会上第一个发言。"),
    ("社交", "给一位合作伙伴打电话而不是发消息。"),
    ("社交", "记住今天见到的三个人的名字。"),
    ("社交", "向同事分享一条对他有用的信息。"),
    ("社交", "参加一次平时不去凑热闹的活动。"),
    ("社交", "主动自我介绍, 认识一位陌生人。"),
    ("社交", "回复那条你一直拖着没回的消息。"),
    ("社交", "当面感谢一位帮过你的人。"),
    ("社交", "问一个人最近在忙什么, 并认真听完。"),
    ("整理", "清空桌面, 只留今天要用的东西。"),
    ("整理", "删掉手机里 20 张废照片。"),
    ("整理", "退订三个从不看的邮件列表或公众号。"),
    ("整理", "清理下载文件夹里超过一年的文件。"),
    ("整理", "把今天要做的三件事写下来。"),
    ("整理", "关掉一个最打扰你的通知。"),
    ("整理", "整理一次电脑桌面图标。"),
    ("整理", "找出三件一年没用的东西, 决定去留。"),
    ("整理", "清空收件箱, 该归档的归档。"),
    ("整理", "写下这周想丢掉的三个坏习惯。"),
]

CATEGORIES = ["善意", "学习", "健康", "探索", "社交", "整理"]
LUCK = ("大吉", "中吉", "小吉")
LUCK_WEIGHTS = (25, 50, 25)


def derive_seed(date_str, category):
    """日期(与类别)字符串经 SHA-256 派生稳定种子。"""
    key = "random-mission|%s|%s" % (date_str, category or "*")
    return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")


def draw_slips(rng, pool, count):
    """从池中不重复抽 count 枚, 并为每枚定吉位。"""
    slips = []
    for item in rng.sample(pool, count):
        no = MISSIONS.index(item) + 1
        luck = LUCK[rng.choices((0, 1, 2), weights=LUCK_WEIGHTS)[0]]
        slips.append((no, item[0], item[1], luck))
    return slips


def _check_category(name):
    if name and name not in CATEGORIES:
        raise ValueError("类别需为: %s" % "/".join(CATEGORIES))
    return name or None


def cmd_draw(args):
    if args.date:
        try:
            date.fromisoformat(args.date)
        except ValueError:
            raise ValueError("--date 需为 YYYY-MM-DD 格式, 如 2026-11-03") from None
        date_str = args.date
    else:
        date_str = date.today().isoformat()
    category = _check_category(args.category)
    pool = [m for m in MISSIONS if category is None or m[0] == category]
    if args.count < 1 or args.count > len(pool):
        raise ValueError("--count 需在 1..%d 之间" % len(pool))
    if args.fresh:
        rng = random.Random()
    else:
        rng = random.Random(derive_seed(date_str, category))
    slips = draw_slips(rng, pool, args.count)
    print("今日任务签 · %s" % date_str)
    for no, cat, text, luck in slips:
        print("第 %d 签 · %s · %s" % (no, cat, luck))
        print("签文: %s" % text)
        if args.count > 1:
            print()
    return 0


def cmd_list(args):
    category = _check_category(args.category)
    shown = 0
    for cat in CATEGORIES:
        if category and cat != category:
            continue
        print("%s:" % cat)
        for i, (c, text) in enumerate(MISSIONS, 1):
            if c == cat:
                print("  %2d. %s" % (i, text))
                shown += 1
    print("共 %d 枚任务签(全库 %d 枚, %d 类)。" % (shown, len(MISSIONS), len(CATEGORIES)))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="random-mission",
        description="抽一枚每日挑战小签(默认同一天结果固定)。")
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="命令")

    sp = sub.add_parser("draw", help="抽签(默认按日期固定)")
    sp.add_argument("--date", default=None, metavar="YYYY-MM-DD",
                    help="指定日期, 缺省为今天")
    sp.add_argument("-c", "--category", default=None,
                    help="限定类别: %s" % "/".join(CATEGORIES))
    sp.add_argument("--count", type=int, default=1, help="连抽枚数(默认 1)")
    sp.add_argument("--fresh", action="store_true",
                    help="完全随机, 不按日期固定")
    sp.set_defaults(func=cmd_draw)

    sp = sub.add_parser("list", help="列出任务签库")
    sp.add_argument("-c", "--category", default=None,
                    help="只列某类别: %s" % "/".join(CATEGORIES))
    sp.set_defaults(func=cmd_list)
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print("random-mission: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
