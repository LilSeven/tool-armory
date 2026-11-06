#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""年积日计算:计算日期为当年第几天及剩余天数;支持由年积日反查日期。

正查:给定日期,输出其为当年第几天、年内已过/剩余天数。
反查:给定年积日(1~365/366)与年份,输出对应日期。

示例命令:
  python day-of-year.py 2026-11-02              # 正查:2026 年第 306 天
  python day-of-year.py 2024-12-31              # 闰年的最后一天为第 366 天
  python day-of-year.py --doy 306 --year 2026   # 反查:2026 年第 306 天是哪天
  python day-of-year.py --doy 366 --year 2024   # 闰年允许 1~366
"""

import argparse
import calendar
import sys
from datetime import date, datetime, timedelta

WEEKDAY_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def parse_date(text):
    """把字符串解析为 date,支持 - / . 三种分隔符。"""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError("无法解析日期 %r(支持 YYYY-MM-DD)" % text)


def year_total_days(year):
    """该年总天数:闰年 366,平年 365。"""
    return 366 if calendar.isleap(year) else 365


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        description="计算日期为当年第几天及剩余天数,或由年积日反查日期")
    parser.add_argument("date", nargs="?", help="日期(YYYY-MM-DD),正查模式")
    parser.add_argument("--doy", type=int, help="年积日,反查模式")
    parser.add_argument("--year", type=int, help="反查模式的年份,缺省为今年")
    args = parser.parse_args(argv)

    if args.doy is not None:
        year = args.year if args.year is not None else date.today().year
        total = year_total_days(year)
        if not 1 <= args.doy <= total:
            parser.error("%d 年共有 %d 天,年积日应在 1~%d 之间" % (year, total, total))
        d = date(year, 1, 1) + timedelta(days=args.doy - 1)
        print("%d 年第 %d 天 → %s(%s)" % (year, args.doy, d.isoformat(), WEEKDAY_CN[d.weekday()]))
        print("%d 年是%s年,全年 %d 天" % (year, "闰" if calendar.isleap(year) else "平", total))
    elif args.date:
        d = parse_date(args.date)
        yday = d.timetuple().tm_yday
        total = year_total_days(d.year)
        print("%s(%s)是 %d 年第 %d 天(全年 %d 天,%s)"
              % (d.isoformat(), WEEKDAY_CN[d.weekday()], d.year, yday, total,
                 "闰年" if calendar.isleap(d.year) else "平年"))
        print("年内已过 %d 天,剩余 %d 天(均不含当天)" % (yday - 1, total - yday))
    else:
        parser.error("请给一个日期做正查,或用 --doy(可配合 --year)做反查,详见 -h")
    return 0


if __name__ == "__main__":
    sys.exit(main())
