#!/usr/bin/env python3
"""美国联邦假日表 —— 按规则生成指定年份美国联邦假日完整日期表。

依据 5 U.S.C. §6103 定义的 11 个联邦假日按规则推算日期:
  固定日期假日（元旦、六月节、独立日、退伍军人节、圣诞节）落在周六则
  观测日提前至周五、落在周日则顺延至周一;
  星期规则假日（马丁·路德·金日、华盛顿诞辰日、阵亡将士纪念日、劳工节、
  哥伦布日、感恩节）按「第 N 个星期 X / 最后一个星期 X」推算。
（就职典礼日为华盛顿哥伦比亚特区等地的地方性假日，不列入本表。）

用法示例:
    python holiday-us.py --year 2026
    python holiday-us.py 2026
    python holiday-us.py --year 2026 --actual   # 仅显示实际日期，不做观测日调整
"""

import argparse
import sys
from datetime import date, timedelta

WEEKDAY_ZH = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def _force_utf8_stdio():
    """让输出在 Windows 管道/重定向下也按 UTF-8 编码（Git Bash 友好）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def nth_weekday(year, month, weekday, n):
    """某月第 n 个「星期 weekday」(0=周一 .. 6=周日)。"""
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def last_weekday(year, month, weekday):
    """某月最后一个「星期 weekday」。"""
    if month == 12:
        last_day = date(year, 12, 31)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    return last_day - timedelta(days=(last_day.weekday() - weekday) % 7)


def federal_holidays(year):
    """返回 [(英文名, 中文名, 实际日期), ...]，按实际日期升序。"""
    items = [
        ("New Year's Day", "元旦", date(year, 1, 1)),
        ("Martin Luther King, Jr. Day", "马丁·路德·金纪念日", nth_weekday(year, 1, 0, 3)),
        ("Washington's Birthday", "华盛顿诞辰日（总统日）", nth_weekday(year, 2, 0, 3)),
        ("Memorial Day", "阵亡将士纪念日", last_weekday(year, 5, 0)),
        ("Juneteenth National Independence Day", "六月节", date(year, 6, 19)),
        ("Independence Day", "独立日", date(year, 7, 4)),
        ("Labor Day", "劳工节", nth_weekday(year, 9, 0, 1)),
        ("Columbus Day", "哥伦布日", nth_weekday(year, 10, 0, 2)),
        ("Veterans Day", "退伍军人节", date(year, 11, 11)),
        ("Thanksgiving Day", "感恩节", nth_weekday(year, 11, 3, 4)),
        ("Christmas Day", "圣诞节", date(year, 12, 25)),
    ]
    items.sort(key=lambda item: item[2])
    return items


def observed(day):
    """观测日: 落在周六提前至周五，落在周日顺延至周一，其余不变。"""
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def main(argv=None):
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="按规则生成指定年份美国联邦假日完整日期表（5 U.S.C. §6103）")
    parser.add_argument("year_pos", nargs="?", type=int, metavar="YYYY",
                        help="年份（默认当前年份）")
    parser.add_argument("--year", type=int, metavar="YYYY", help="年份")
    parser.add_argument("--actual", action="store_true",
                        help="仅显示实际日期，不做观测日调整")
    args = parser.parse_args(argv)

    if args.year is not None and args.year_pos is not None and args.year != args.year_pos:
        parser.error("位置参数与 --year 冲突")
    year = args.year if args.year is not None else args.year_pos
    if year is None:
        year = date.today().year
    if not 1 <= year <= 9999:
        parser.error("年份应在 1-9999 之间")

    items = federal_holidays(year)
    if args.actual:
        print("%d 年美国联邦假日（共 %d 个，按实际日期，不做观测日调整）"
              % (year, len(items)))
        for en, zh, actual in items:
            print("  %s（%s）  %s（%s）"
                  % (actual.isoformat(), WEEKDAY_ZH[actual.weekday()], en, zh))
        return 0

    rows = sorted(((observed(a), en, zh, a) for en, zh, a in items),
                  key=lambda r: r[0])
    print("%d 年美国联邦假日（共 %d 个；观测日按 5 U.S.C. §6103 调整）"
          % (year, len(rows)))
    for obs, en, zh, actual in rows:
        if actual.weekday() == 5:
            note = "  [周六，提前至周五观测]"
        elif actual.weekday() == 6:
            note = "  [周日，顺延至周一观测]"
        else:
            note = ""
        print("  %s（%s）  实际 %s  %s（%s）%s"
              % (obs.isoformat(), WEEKDAY_ZH[obs.weekday()],
                 actual.isoformat(), en, zh, note))
    return 0


if __name__ == "__main__":
    sys.exit(main())
