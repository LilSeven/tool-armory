#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""星座配对 —— 输入两人生成趣味配对指数与毒舌评语。

用途:
    输入两个人（名字 + 星座或生日），输出一张趣味配对报告：
    配对指数、相性标签、毒舌评语、谁先低头与相处建议。
    星座可写"白羊座"，也可写生日"03-28"/"3月28日"/"1995-03-28"；
    只写名字则随机分配星座。同一对输入结果固定。纯属娱乐。

用法:
    python constellation-assign.py 小明:白羊座 小红:天蝎座
    python constellation-assign.py 小明:03-28 小红:7月14日
    python constellation-assign.py 小明 小红 --seed 42

示例命令:
    python constellation-assign.py 小明:白羊座 小红:天蝎座
"""

from __future__ import annotations

import argparse
import random
import re
import sys

# (星座, 起始月, 起始日, 结束月, 结束日)；摩羯座跨年，sign_for 里特殊判断
SIGNS = [
    ("白羊座", 3, 21, 4, 19),
    ("金牛座", 4, 20, 5, 20),
    ("双子座", 5, 21, 6, 21),
    ("巨蟹座", 6, 22, 7, 22),
    ("狮子座", 7, 23, 8, 22),
    ("处女座", 8, 23, 9, 22),
    ("天秤座", 9, 23, 10, 23),
    ("天蝎座", 10, 24, 11, 22),
    ("射手座", 11, 23, 12, 21),
    ("水瓶座", 1, 20, 2, 18),
    ("双鱼座", 2, 19, 3, 20),
    ("摩羯座", 12, 22, 1, 19),
]
SIGN_NAMES = [name for name, *_ in SIGNS]

SIGN_ALIASES = {
    "白羊": "白羊座", "牡羊": "白羊座", "牡羊座": "白羊座",
    "金牛": "金牛座", "双子": "双子座", "巨蟹": "巨蟹座",
    "狮子": "狮子座", "处女": "处女座",
    "天平": "天秤座", "天平座": "天秤座",
    "天蝎": "天蝎座", "射手": "射手座",
    "摩羯": "摩羯座", "魔羯": "摩羯座", "魔羯座": "摩羯座",
    "水瓶": "水瓶座", "双鱼": "双鱼座",
    "aries": "白羊座", "taurus": "金牛座", "gemini": "双子座",
    "cancer": "巨蟹座", "leo": "狮子座", "virgo": "处女座",
    "libra": "天秤座", "scorpio": "天蝎座", "sagittarius": "射手座",
    "capricorn": "摩羯座", "aquarius": "水瓶座", "pisces": "双鱼座",
}

SNARKS = [
    "你们聊天像 WiFi：时满格时断联，但谁也不肯先重启。",
    "一个说'随便'，一个真随便，命运让你们相遇不是没有原因的。",
    "你们的感情像便利店的关东煮：便宜、顶饱、深夜才香。",
    "在一起之后，你们的备忘录会比聊天记录还长。",
    "别人谈恋爱送花，你们谈恋爱送表情包，量大管饱。",
    "你们吵架的胜负手不在嗓门，在谁先说'行行行'。",
    "这段关系唯一的稳定输出，是互相吐槽第三人。",
    "一个爱计划，一个爱放鸽子，日程表表示压力很大。",
    "你们是彼此的减压阀，也是彼此的血压来源。",
    "你们的默契在于：同时想吃饭，永远想不出吃什么。",
    "缘分不重要，重要的是谁抢到了遥控器。",
    "你们像两台系统不同但都能用的手机：同步不了日程，但都能扫码。",
    "别问配不配，先问问谁先改掉已读乱回。",
    "你们的 romance 是：互相嫌弃，但外人不能说。",
]

BOWS = [
    "指数高的时候，谁错谁低头；指数低的时候，谁饿谁低头。",
    "冷战的尽头是'外卖到了'。",
    "理论上更理智的那位先低头——可惜你们都在装理智。",
    "建议掷硬币：输的道歉，赢的复盘。",
    "都别装了，你已经在打字了。",
]

ADVICES = [
    "每周留一顿'不聊正事'的饭，感情保温靠废话。",
    "吵架不过夜；实在过夜，也要先说好'明天继续吵'。",
    "重要决定一起拍板，小决定交给石头剪刀布。",
    "把'在吗'换成'说事'，好感度直接 +10。",
    "记住对方的忌口，比记住纪念日更救命。",
    "允许对方每周独处半天，电子含量过高会死机。",
    "旅行前先分好工：一个订票，一个负责夸订得好。",
    "生气时先喝口水再发言，水是你们共同的朋友。",
]


def _setup_stdio() -> None:
    """尽力把输出流切到 UTF-8，避免 Windows 控制台中文/表情乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def sign_for(month: int, day: int) -> str:
    """按月日返回星座名。"""
    if (month == 12 and day >= 22) or (month == 1 and day <= 19):
        return "摩羯座"
    for name, m1, d1, m2, d2 in SIGNS:
        if name == "摩羯座":
            continue
        if (month, day) >= (m1, d1) and (month, day) <= (m2, d2):
            return name
    raise ValueError(f"无法识别的日期：{month}-{day}")


def parse_person(spec: str) -> tuple[str, str | None]:
    """解析'名字[:星座|生日]'，返回 (名字, 星座名或 None)。"""
    for sep in ("：", ":"):
        if sep in spec:
            name, tag = spec.split(sep, 1)
            break
    else:
        name, tag = spec, ""
    name = name.strip() or "路人"
    tag = tag.strip()
    if not tag:
        return name, None
    if tag in SIGN_NAMES:
        return name, tag
    key = tag.lower() if tag.isascii() else tag
    if key in SIGN_ALIASES:
        return name, SIGN_ALIASES[key]
    if tag.endswith("座") and tag[:-1] in SIGN_ALIASES:
        return name, SIGN_ALIASES[tag[:-1]]
    m = re.match(r"^(?:\d{4}[-/年.])?\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})\s*日?$", tag)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return name, sign_for(month, day)
    raise ValueError(
        f"看不懂「{tag}」：请用星座名（如 白羊座）或生日（如 03-28、3月28日、1995-03-28）")


def band(score: int) -> str:
    if score >= 90:
        return "天作之合（建议直接锁死）"
    if score >= 75:
        return "相当来电，注意节约电费"
    if score >= 60:
        return "有戏，但需要一部连续剧的耐心"
    if score >= 40:
        return "互补型选手，互补到互相补刀"
    return "塑料缘分，组队打副本倒是很合适"


def make_report(name1: str, sign1: str | None, name2: str, sign2: str | None,
                seed: int | None) -> str:
    key = "|".join(sorted([f"{name1}|{sign1 or '随机'}",
                           f"{name2}|{sign2 or '随机'}"]))
    rng = random.Random(seed if seed is not None else f"pair|{key}")
    if sign1 is None:
        sign1 = rng.choice(SIGN_NAMES)
    if sign2 is None:
        sign2 = rng.choice(SIGN_NAMES)
    score = rng.randint(28, 99)
    snark = rng.choice(SNARKS)
    bow = rng.choice(BOWS)
    advice = rng.choice(ADVICES)

    lines = [
        "💘 星座配对报告（玩具版）",
        f"  左盘：{name1}（{sign1}） × 右盘：{name2}（{sign2}）",
        f"  配对指数：{score} / 100",
        f"  相性标签：{band(score)}",
        f"  毒舌评语：{snark}",
    ]
    if sign1 == sign2:
        lines.append("  同星座加成：你们连拖延的借口都一模一样，省心又省事。")
    lines += [
        f"  谁先低头：{bow}",
        f"  相处建议：{advice}",
        "  （配对结果纯属娱乐，感情请以真人实测为准。）",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="constellation-assign.py",
        description="星座配对 —— 输入两人生成趣味配对指数与毒舌评语。",
    )
    parser.add_argument("person1", help="第一位：名字[:星座|生日]，如 小明:白羊座")
    parser.add_argument("person2", help="第二位：名字[:星座|生日]，如 小红:7月14日")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子，固定后结果可复现")
    return parser


def main(argv: list[str] | None = None) -> int:
    _setup_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        name1, sign1 = parse_person(args.person1)
        name2, sign2 = parse_person(args.person2)
    except ValueError as exc:
        parser.error(str(exc))  # 退出码 2
    print(make_report(name1, sign1, name2, sign2, args.seed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
