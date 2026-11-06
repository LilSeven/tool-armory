#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日星运 —— 按日期种子为十二星座生成今日运势与幸运色。

以"日期 + 星座"为随机种子，为每个星座生成整体/爱情/事业/财运/健康
五项指数（同一天结果固定不变）、幸运色与幸运数字，并附今日提点。
仅依赖 Python 标准库。

用法：
    python horoscope-daily.py                           # 全部十二星座（今天）
    python horoscope-daily.py --sign 双鱼座 --date 2026-11-03
    python horoscope-daily.py --sign aries              # 英文名亦可
    python horoscope-daily.py --birthday 1995-08-20     # 按生日定星座
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import random
import sys

# (中文, 英文, 符号, 起始(月,日), 结束(月,日))
SIGNS = (
    ("白羊座", "Aries", "♈", (3, 21), (4, 19)),
    ("金牛座", "Taurus", "♉", (4, 20), (5, 20)),
    ("双子座", "Gemini", "♊", (5, 21), (6, 21)),
    ("巨蟹座", "Cancer", "♋", (6, 22), (7, 22)),
    ("狮子座", "Leo", "♌", (7, 23), (8, 22)),
    ("处女座", "Virgo", "♍", (8, 23), (9, 22)),
    ("天秤座", "Libra", "♎", (9, 23), (10, 23)),
    ("天蝎座", "Scorpio", "♏", (10, 24), (11, 22)),
    ("射手座", "Sagittarius", "♐", (11, 23), (12, 21)),
    ("摩羯座", "Capricorn", "♑", (12, 22), (1, 19)),
    ("水瓶座", "Aquarius", "♒", (1, 20), (2, 18)),
    ("双鱼座", "Pisces", "♓", (2, 19), (3, 20)),
)

ASPECTS = ("爱情", "事业", "财运", "健康")

COLORS = (
    "朱红", "海盐蓝", "琥珀金", "橄榄绿", "月光白", "藕荷粉",
    "雾灰蓝", "酒红", "湖水青", "驼色", "电光紫", "薄荷绿",
    "暖沙色", "墨绿", "樱花粉", "宫廷蓝", "姜黄", "烟灰粉",
    "松石绿", "勃艮第红", "云朵白", "深空灰", "落日橙", "薰衣草紫",
)

TIPS = {
    "high": (
        "今日运势高走，宜主动出击，把最想做的事排在第一位。",
        "星象明亮，谈判与表白皆宜，机会青睐先开口的人。",
        "状态在线的一天，难啃的任务放在上午事半功倍。",
        "气场开挂，出门记得带点野心，回报会超出预期。",
    ),
    "mid": (
        "整体平稳，按计划推进即可，不必强求突破。",
        "小有起伏，遇到岔路时选让自己心安的那条。",
        "宜守不宜攻的一天，把细节打磨好就是赢。",
        "节奏平缓，适合复盘与整理，为后续蓄力。",
    ),
    "low": (
        "运势低伏，多做少说，避开是非漩涡。",
        "今日宜收缩战线，重要决定缓一天再做。",
        "状态欠佳，早点休息比硬撑更有产出。",
        "谨慎为先，钱包与口舌都看紧一点。",
    ),
}


def _date_arg(value: str) -> _dt.date:
    try:
        return _dt.date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"日期格式应为 YYYY-MM-DD，收到：{value!r}")


def _md(d: _dt.date):
    return (d.month, d.day)


def sign_by_date(d: _dt.date) -> str:
    """按生日（月/日）推断星座中文名。"""
    for zh, _en, _sym, start, end in SIGNS:
        if start <= end:
            if start <= _md(d) <= end:
                return zh
        else:  # 摩羯座跨年
            if _md(d) >= start or _md(d) <= end:
                return zh
    raise RuntimeError("生日未能匹配星座，检查 SIGNS 表")


def resolve_sign(name: str) -> str:
    """按中文名或英文名（不区分大小写）解析星座。"""
    for zh, en, *_ in SIGNS:
        if name in (zh, en.lower()):
            return zh
    raise argparse.ArgumentTypeError(
        f"未知星座：{name!r}，可用：" +
        "、".join(z for zh, *_ in SIGNS for zh in [zh]) +
        " 或 all")


def stars(score: int) -> str:
    n = max(1, min(5, round(score / 20)))
    return "★" * n + "☆" * (5 - n)


def horoscope(sign_zh: str, day: _dt.date) -> dict:
    seed = hashlib.sha256(
        f"horoscope|{day.isoformat()}|{sign_zh}".encode("utf-8")).hexdigest()
    rng = random.Random(seed)
    overall = rng.randint(45, 95)
    aspects = {
        a: max(25, min(98, overall + rng.randint(-22, 22)))
        for a in ASPECTS
    }
    bucket = "high" if overall >= 80 else ("mid" if overall >= 60 else "low")
    return {
        "overall": overall,
        "aspects": aspects,
        "color": rng.choice(COLORS),
        "number": rng.randint(1, 99),
        "tip": rng.choice(TIPS[bucket]),
    }


def render(sign_zh: str, day: _dt.date) -> str:
    zh, en, sym, *_ = next(s for s in SIGNS if s[0] == sign_zh)
    data = horoscope(sign_zh, day)
    parts = [f"{sym} {zh} {en} · {day.isoformat()}",
             f"整体运势 {stars(data['overall'])} {data['overall']}"]
    parts.append(" ｜ ".join(
        f"{a} {stars(v)} {v}" for a, v in data["aspects"].items()))
    parts.append(f"幸运色：{data['color']} ｜ 幸运数字：{data['number']}")
    parts.append(f"今日提点：{data['tip']}")
    return "\n".join(parts)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="horoscope-daily",
        description="按日期种子为十二星座生成今日运势与幸运色")
    parser.add_argument("--date", type=_date_arg, default=None,
                        help="日期（默认今天），格式 YYYY-MM-DD")
    parser.add_argument("--sign", default="all",
                        help="星座中文名/英文名，或 all（默认全部）")
    parser.add_argument("--birthday", type=_date_arg, default=None,
                        help="按生日推断星座，优先于 --sign")
    args = parser.parse_args(argv)

    day = args.date or _dt.date.today()
    if args.birthday is not None:
        sign = sign_by_date(args.birthday)
    elif args.sign.strip().lower() == "all":
        sign = "all"
    else:
        sign = resolve_sign(args.sign.strip())

    targets = [s[0] for s in SIGNS] if sign == "all" else [sign]
    for i, t in enumerate(targets):
        if i:
            print()
        print(render(t, day))
    return 0


if __name__ == "__main__":
    sys.exit(main())
