#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""今日人设卡 —— 随机生成一张含属性、弱点、技能的每日人设卡。

用途:
    以「日期 + 名字」为种子，每天为一个人生成一张固定的人设卡，
    含称号、阵营、六维属性（星级+数值+短评）、弱点、技能与今日断言。
    同一天同名同卡，隔天自动翻新。纯属娱乐，请勿写进简历。

用法:
    python personality-fortune.py 小明
    python personality-fortune.py 小红 --date 2026-11-03
    python personality-fortune.py 老王 --seed 42

示例命令:
    python personality-fortune.py 小明 --date 2026-11-03
"""

from __future__ import annotations

import argparse
import datetime
import random
import sys

STAT_LABELS = ["颜值", "智力", "体力", "运气", "魅力", "抗压"]

PREFIXES = ["赛博", "退休预备役", "人间清醒", "深夜emo", "工位钉子户",
            "满级", "半糖", "随机掉落", "传说级"]
TITLES = ["摸鱼大师", "干饭王", "熬夜冠军", "社交猎人", "选择题杀手",
          "废话文学家", "氛围担当", "碎钞机战士", "金句制造机"]
CAMPS = ["摸鱼阵营", "早八阵营", "夜猫子阵营", "干饭阵营", "养生朋克阵营",
         "社恐阵营", "社牛阵营", "躺平主义阵营", "咖啡因依赖阵营"]

WEAKNESSES = [
    "周一综合症（持续一整周）",
    "听到'在吗'就心慌",
    "外卖满减永远算不明白",
    "一开会就开始点头钉钉",
    "回消息全靠缘分",
    "存钱系统常年负优化",
    "被当众点名就大脑蓝屏",
    "奶茶戒断反应严重",
]

SKILLS = [
    "三分钟装出很忙的样子",
    "在嘈杂地铁上精准补觉",
    "把任何话题自然聊到吃的",
    "deadline 前夜爆发式赶工",
    "用表情包精准化解尴尬",
    "一句话让整个群冷场",
    "识破老板的'简单加个班'",
    "断网也能活过一整个下午",
]

ASSERTIONS = [
    "今天你的气场比昨天稳定，适合谈判、谈钱、谈加薪。",
    "今天说'不'的收益大于说'好'，酌情使用。",
    "今天的小事会连环顺利，攒够三件请停止，防止骄傲。",
    "今天容易遇到'话痨型贵人'，信息量很大，注意筛。",
    "今天的你要相信第一直觉，第二直觉是饿了。",
    "今天不宜立 flag，宜悄悄把事办了再惊艳所有人。",
]


def _setup_stdio() -> None:
    """尽力把输出流切到 UTF-8，避免 Windows 控制台中文/表情乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _parse_date(text: str) -> datetime.date:
    """解析 YYYY-MM-DD / YYYY/MM/DD，失败抛 ArgumentTypeError。"""
    try:
        y, m, d = (int(p) for p in text.replace("/", "-").split("-"))
        return datetime.date(y, m, d)
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError(f"日期格式应为 YYYY-MM-DD，收到：{text!r}")


def _grade(v: int) -> str:
    if v >= 90:
        return "逆天"
    if v >= 75:
        return "优秀"
    if v >= 50:
        return "能打"
    if v >= 30:
        return "及格边缘"
    return "重在参与"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="personality-fortune.py",
        description="今日人设卡 —— 随机生成一张含属性、弱点、技能的每日人设卡。",
    )
    parser.add_argument("name", nargs="?", default="路人甲",
                        help="人设卡主角的名字（可选，默认'路人甲'）")
    parser.add_argument("--date", type=_parse_date, default=None,
                        help="指定日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子，固定后忽略日期直接复现")
    return parser


def make_card(name: str, day: datetime.date, seed: int | None) -> str:
    """生成一张每日人设卡：同日同名结果固定。"""
    rng = random.Random(seed if seed is not None
                        else f"persona|{day.isoformat()}|{name}")
    title = f"{rng.choice(PREFIXES)}·{rng.choice(TITLES)}"
    camp = rng.choice(CAMPS)
    stats = [(label, rng.randint(1, 100)) for label in STAT_LABELS]
    weaknesses = rng.sample(WEAKNESSES, 2)
    skills = rng.sample(SKILLS, 2)
    assertion = rng.choice(ASSERTIONS)

    lines = [
        "┌───────────────────────────────",
        f" 今日人设卡 · {day.isoformat()}",
        f" 姓名：{name}",
        f" 称号：{title}",
        f" 阵营：{camp}",
        "───────────────────────────────",
        " 六维属性：",
    ]
    for label, v in stats:
        stars = "★" * (v // 20) + "☆" * (5 - v // 20)
        lines.append(f"   {label}  {stars}  {v:>3}  {_grade(v)}")
    lines += [
        "───────────────────────────────",
        f" 弱点：{weaknesses[0]}；{weaknesses[1]}",
        f" 技能：{skills[0]}；{skills[1]}",
        f" 今日断言：{assertion}",
        "└───────────────────────────────",
        "（同日同名同卡，隔天自动翻新；纯属娱乐，请勿写进简历。）",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    _setup_stdio()
    args = build_parser().parse_args(argv)
    day = args.date if args.date is not None else datetime.date.today()
    print(make_card(args.name, day, args.seed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
