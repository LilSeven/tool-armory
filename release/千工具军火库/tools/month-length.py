#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""月天数查询:输出某年某月的天数与月末日期;也可列出全年各月天数一览。

示例命令:
  python month-length.py 2026 2    # 2026 年 2 月:28 天,月末 2026-02-28
  python month-length.py 2024 2    # 闰年 2 月:29 天,月末 2024-02-29
  python month-length.py 2026      # 2026 年 1~12 月天数一览
"""

import argparse
import calendar
import sys
from datetime import date

WEEKDAY_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        description="查询某年某月的天数与月末日期,或列出全年各月天数一览")
    parser.add_argument("year", type=int, help="年份,如 2026")
    parser.add_argument("month", type=int, nargs="?",
                        help="月份 1~12;省略则输出全年一览")
    args = parser.parse_args(argv)

    year = args.year
    if not 1 <= year <= 9999:
        parser.error("年份须在 1~9999 之间")

    if args.month is None:
        leap = calendar.isleap(year)
        print("%d 年是%s年,全年 %d 天;各月天数如下:"
              % (year, "闰" if leap else "平", 366 if leap else 365))
        for m in range(1, 13):
            days = calendar.monthrange(year, m)[1]
            last = date(year, m, days)
            print("  %2d 月: %2d 天,月末 %s(%s)"
                  % (m, days, last.isoformat(), WEEKDAY_CN[last.weekday()]))
    else:
        month = args.month
        if not 1 <= month <= 12:
            parser.error("月份须在 1~12 之间")
        days = calendar.monthrange(year, month)[1]
        first, last = date(year, month, 1), date(year, month, days)
        print("%d 年 %d 月共有 %d 天" % (year, month, days))
        print("范围:%s(%s) 至 %s(%s)"
              % (first.isoformat(), WEEKDAY_CN[first.weekday()],
                 last.isoformat(), WEEKDAY_CN[last.weekday()]))
        if month == 2:
            print("%d 年是%s年,2 月为 %d 天"
                  % (year, "闰" if calendar.isleap(year) else "平",
                     29 if calendar.isleap(year) else 28))
    return 0


if __name__ == "__main__":
    sys.exit(main())
