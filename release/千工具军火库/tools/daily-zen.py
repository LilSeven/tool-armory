#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daily-zen.py — 禅意一句话：按日期输出一句伪禅语公案，附带木鱼提示符。

同一日期输出恒定（由日期字符串的 MD5 确定性选则），不同日期通常不同；
仅用 Python 标准库（argparse / datetime / hashlib / sys）。

用法:
    python daily-zen.py                     # 今天的公案
    python daily-zen.py --date 2026-11-03   # 指定日期的公案
    python daily-zen.py --date 2026-11-03 --plain   # 去掉木鱼提示符，纯文本
    python daily-zen.py --list              # 列出全部公案后退出

示例:
    $ python -I daily-zen.py --date 2026-11-03
    木鱼> 笃、笃、笃 ——
    木鱼> 上座，今日公案（2026-11-03 · 星期二 · 第22则）：
    木鱼>     「今日事今日毕。」
    木鱼>       —— 明日复有明日事，此亦无常。
    木鱼> 笃。善哉，善哉。
"""

import argparse
import datetime as _dt
import hashlib
import sys

# (公案正文, 落款小注) —— 伪禅语，参禅参不好也别怪木鱼
KOANS = [
    ("一花一世界，一叶一菩提。", "一格一报错，一行一轮回。"),
    ("风未动，幡未动。", "是你的分支在动。"),
    ("本来无一物，何处惹尘埃？", "本来无一文档，何处惹需求。"),
    ("放下即是拥有。", "比如放下那条改了三百行的重构分支。"),
    ("吃饭时吃饭，睡觉时睡觉。", "调试时调试，莫想离职。"),
    ("菩提本无树，明镜亦非台。", "服务器本无根，宕机亦非灾。"),
    ("磨砖不能成镜，坐禅岂能成佛？", "加班岂能上线？"),
    ("云在青天水在瓶。", "Bug 在测试，事故在生产。"),
    ("色即是空。", "缓存即是空——TTL 一到，自然空。"),
    ("不怕念起，只怕觉迟。", "不怕报错，只怕告警迟了三天。"),
    ("万法归一，一归何处？", "千支百支，终归 main。"),
    ("道在日常。", "道也在 crontab 里，五更即起。"),
    ("你从何处来？", "git blame 知道。"),
    ("无常。", "版本号亦无常，昨日还叫 2.0。"),
    ("桶底脱落。", "磁盘亦然，深夜三时，桶底洞然。"),
    ("一日不作，一日不食。", "一日不提交，一日不安。"),
    ("饥来吃饭困来眠。", "需求来了就改，改完再谈需求。"),
    ("乾坤一钵，云水一生。", "笔记本一肩，从工位到天涯。"),
    ("且吃茶去。", "CI 还在跑，且吃茶去。"),
    ("十方无影像。", "镜像拉不下来，容器无从生。"),
    ("若人识得心，大地无寸土。", "若人识得根目录，磁盘皆虚空。"),
    ("今日事今日毕。", "明日复有明日事，此亦无常。"),
    ("如何是佛？", "先把这行改对。"),
    ("不雨花犹落，无风絮自飞。", "无改码自崩，此机玄之又玄。"),
]

WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

PROMPT = "木鱼> "  # 木鱼提示符


def pick_koan(d):
    """按日期确定性挑一则公案：同一日期永远同一句。"""
    digest = hashlib.md5(d.isoformat().encode("utf-8")).hexdigest()
    idx = int(digest, 16) % len(KOANS)
    return idx, KOANS[idx]


def render(d, plain=False):
    """渲染一日公案为多行字符串。"""
    idx, (body, note) = pick_koan(d)
    wd = WEEKDAYS[d.weekday()]
    head = "%s · %s · 第%02d则" % (d.isoformat(), wd, idx + 1)
    if plain:
        return "\n".join([head, "「%s」—— %s" % (body, note), "笃。"])
    return "\n".join([
        PROMPT + "笃、笃、笃 ——",
        PROMPT + "上座，今日公案（%s）：" % head,
        PROMPT + "    「%s」" % body,
        PROMPT + "      —— %s" % note,
        PROMPT + "笃。善哉，善哉。",
    ])


def main(argv=None):
    # Git Bash 管道下 stdout 可能回落到本地编码（如 cp936），
    # 统一改用 UTF-8 输出，替换不可编码字符以免崩溃。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    parser = argparse.ArgumentParser(
        prog="daily-zen",
        description="按日期输出一句伪禅语公案，附带木鱼提示符。同一日期输出恒定。",
    )
    parser.add_argument(
        "--date", dest="date", default=None, metavar="YYYY-MM-DD",
        help="日期 YYYY-MM-DD（缺省为今天）",
    )
    parser.add_argument(
        "--plain", action="store_true", help="去掉木鱼提示符，输出纯文本",
    )
    parser.add_argument(
        "--list", action="store_true", help="列出全部公案后退出",
    )
    args = parser.parse_args(argv)

    if args.list:
        for i, (body, note) in enumerate(KOANS, 1):
            print("%02d. 「%s」—— %s" % (i, body, note))
        return 0

    if args.date is None:
        d = _dt.date.today()
    else:
        try:
            d = _dt.date.fromisoformat(args.date)
        except ValueError:
            print("错误：日期「%s」不是合法的 YYYY-MM-DD。" % args.date,
                  file=sys.stderr)
            return 2

    print(render(d, plain=args.plain))
    return 0


if __name__ == "__main__":
    sys.exit(main())
