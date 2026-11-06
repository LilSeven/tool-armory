#!/usr/bin/env python3
"""西方星座查询（Western Zodiac by birth date）。

按公历出生日期（--date YYYY-MM-DD）判断所属星座；不带 --date 时列出
全部 12 个星座的日期边界。

仅用 Python 标准库，单文件。

示例命令：
    python -I zodiac-west.py --date 2000-08-08
    python -I zodiac-west.py                 # 列出各星座日期边界
    python -I zodiac-west.py --date 12-25    # 缺年份也可（只看月日）
"""

from __future__ import annotations

import argparse
import sys

# (名称, 英文名, 起始月, 起始日, 结束月, 结束日)
SIGNS = [
    ("白羊座", "Aries", 3, 21, 4, 19),
    ("金牛座", "Taurus", 4, 20, 5, 20),
    ("双子座", "Gemini", 5, 21, 6, 21),
    ("巨蟹座", "Cancer", 6, 22, 7, 22),
    ("狮子座", "Leo", 7, 23, 8, 22),
    ("处女座", "Virgo", 8, 23, 9, 22),
    ("天秤座", "Libra", 9, 23, 10, 23),
    ("天蝎座", "Scorpio", 10, 24, 11, 22),
    ("射手座", "Sagittarius", 11, 23, 12, 21),
    ("摩羯座", "Capricorn", 12, 22, 1, 19),
    ("水瓶座", "Aquarius", 1, 20, 2, 18),
    ("双鱼座", "Pisces", 2, 19, 3, 20),
]


def sign_for(month: int, day: int) -> str:
    """返回 (中文名, 英文名, 区间描述)。month/day 必须是合法公历月日。"""
    for zh, en, sm, sd, em, ed in SIGNS:
        if sm == em:  # 不会发生，防御
            continue
        if sm <= em:
            if (month, day) >= (sm, sd) and (month, day) <= (em, ed):
                return zh, en, f"{sm:02d}-{sd:02d} ~ {em:02d}-{ed:02d}"
        else:  # 摩羯座跨年
            if (month, day) >= (sm, sd) or (month, day) <= (em, ed):
                return zh, en, f"{sm:02d}-{sd:02d} ~ 次年{em:02d}-{ed:02d}"
    raise AssertionError("unreachable: all (month, day) should match a sign")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="按出生日期判断西方星座")
    ap.add_argument("--date", help="出生日期，YYYY-MM-DD（年份可省略为 MM-DD）")
    ap.add_argument("--all", action="store_true", help="列出全部星座日期边界")
    ns = ap.parse_args(argv)

    if ns.all or not ns.date:
        if ns.date is None and not ns.all:
            print("未提供 --date，列出全部星座日期边界：")
        print(f"{'星座':<6} {'英文名':<12} 日期范围")
        for zh, en, sm, sd, em, ed in SIGNS:
            rng = f"{sm:02d}-{sd:02d} ~ {em:02d}-{ed:02d}"
            if sm > em:
                rng = f"{sm:02d}-{sd:02d} ~ 次年{em:02d}-{ed:02d}"
            print(f"{zh:<6} {en:<12} {rng}")
        return 0

    parts = ns.date.split("-")
    if len(parts) == 2:
        month_s, day_s = parts
        year_note = "（未提供年份，仅按月日判断）"
    elif len(parts) == 3:
        year_s, month_s, day_s = parts
        year_note = ""
        if not (1 <= int(year_s) <= 9999):
            print(f"错误：年份 {year_s} 不合法", file=sys.stderr)
            return 2
    else:
        print(f"错误：日期格式应为 YYYY-MM-DD 或 MM-DD，得到 {ns.date!r}", file=sys.stderr)
        return 2
    try:
        month, day = int(month_s), int(day_s)
    except ValueError:
        print(f"错误：月/日不是数字：{ns.date!r}", file=sys.stderr)
        return 2

    # 用 calendar.monthrange 校验该月该日真实存在
    import calendar
    year = 2000 if len(parts) == 2 else int(year_s)
    if not (1 <= month <= 12) or not (1 <= day <= calendar.monthrange(year, month)[1]):
        print(f"错误：{month:02d}-{day:02d} 不是合法的公历日期", file=sys.stderr)
        return 2

    zh, en, rng = sign_for(month, day)
    print(f"出生日期 {ns.date}{year_note}")
    print(f"星座：{zh}（{en}），日期范围 {rng}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
