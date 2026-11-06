#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""教学周计算：按学期开学日计算某日期处于第几教学周，或由周次反查该周日期区间。

示例命令:
  # 计算某日期（默认今天）处于第几教学周，并给出本周区间
  python school-week.py --start 2026-09-01 --date 2026-09-15

  # 由周次反查该教学周的日期区间
  python school-week.py --start 2026-09-01 --week 3

规则:
  教学周按"开学日 + 7*(n-1) 天"滚动划分：开学日所在的 7 天窗口为第 1 周，
  不与自然周的周一强制对齐。
"""

import argparse
import sys
from datetime import date, timedelta

WEEKDAY_CN = ("一", "二", "三", "四", "五", "六", "日")
ONE_WEEK = timedelta(days=7)


def parse_date(text):
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError("日期格式应为 YYYY-MM-DD，收到: %r" % text)


def teaching_week(start, day):
    """返回 day 处于第几教学周（开学日所在 7 天窗口为第 1 周）。"""
    return (day - start).days // 7 + 1


def week_range(start, week):
    """返回第 week 教学周的 (首日, 末日)。"""
    first = start + ONE_WEEK * (week - 1)
    return first, first + timedelta(days=6)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="school-week.py",
        description="教学周计算：由开学日推算第几教学周，或由周次反查日期区间。",
    )
    parser.add_argument("--start", required=True, type=parse_date,
                        help="学期开学日 YYYY-MM-DD（第 1 教学周的第 1 天）")
    parser.add_argument("--date", type=parse_date, default=None,
                        help="要计算的日期 YYYY-MM-DD（缺省为今天）")
    parser.add_argument("--week", type=int, default=None,
                        help="周次 N：反查第 N 教学周的日期区间（给出时忽略 --date）")
    return parser


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    start = args.start

    if args.week is not None:
        if args.week < 1:
            print("错误: 周次必须为 >= 1 的整数", file=sys.stderr)
            return 1
        first, last = week_range(start, args.week)
        print("第 %d 教学周: %s ~ %s" % (args.week, first.isoformat(), last.isoformat()))
        return 0

    day = args.date if args.date is not None else date.today()
    if day < start:
        print("错误: %s 早于开学日 %s，尚未开学" % (day.isoformat(), start.isoformat()),
              file=sys.stderr)
        return 1

    week = teaching_week(start, day)
    day_in_week = (day - start).days % 7 + 1
    first, last = week_range(start, week)
    print("%s（周%s）处于第 %d 教学周，为本周第 %d 天"
          % (day.isoformat(), WEEKDAY_CN[day.weekday()], week, day_in_week))
    print("本周区间: %s ~ %s" % (first.isoformat(), last.isoformat()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
