#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""财年季度计算：按自定义财年起始月，计算日期所属财年与财季，并给出财年/财季起止日期。

示例命令:
  # 财年从 4 月开始（如日本企业惯例），计算 2026-11-02 所属财年财季
  python fiscal-quarter.py --start-month 4 --date 2026-11-02

  # 自然财年（起始月为 1 月，默认），按今天计算
  python fiscal-quarter.py

  # 财年编号取结束年份（如美国联邦政府 FY 惯例）
  python fiscal-quarter.py --start-month 10 --date 2026-11-02 --label end

规则:
  --start-month M 表示财年从 M 月 1 日开始，到次年 M 月 1 日的前一天结束；
  财年编号默认取财年开始的年份（--label end 改为取结束年份）。
"""

import argparse
import calendar
import sys
from datetime import date, timedelta


def parse_date(text):
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError("日期格式应为 YYYY-MM-DD，收到: %r" % text)


def parse_month(text):
    try:
        value = int(text)
    except ValueError:
        value = 0
    if not 1 <= value <= 12:
        raise argparse.ArgumentTypeError("财年起始月应为 1-12 的整数，收到: %r" % text)
    return value


def add_months(day, months):
    """从 day 平移 months 个自然月（日超过目标月天数时取月末）。"""
    index = day.year * 12 + (day.month - 1) + months
    year, month0 = divmod(index, 12)
    month = month0 + 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last))


def locate_fiscal(day, start_month):
    """返回 (财年起始年份, 财季 1-4)。"""
    if day.month >= start_month:
        fy = day.year
    else:
        fy = day.year - 1
    offset = (day.month - start_month) % 12
    quarter = offset // 3 + 1
    return fy, quarter


def fiscal_year_range(fy, start_month):
    """返回编号为 fy 的财年 (起, 止)，编号取财年开始的年份。"""
    start = date(fy, start_month, 1)
    end = add_months(start, 12) - timedelta(days=1)
    return start, end


def build_parser():
    parser = argparse.ArgumentParser(
        prog="fiscal-quarter.py",
        description="按自定义财年起始月，计算日期所属财年财季与季度起止日期。",
    )
    parser.add_argument("--date", type=parse_date, default=None,
                        help="目标日期 YYYY-MM-DD（缺省为今天）")
    parser.add_argument("--start-month", type=parse_month, default=1,
                        help="财年起始月 1-12（缺省 1，即自然年）")
    parser.add_argument("--label", choices=("start", "end"), default="start",
                        help="财年编号取财年开始年份(start，默认)或结束年份(end)")
    return parser


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)

    day = args.date if args.date is not None else date.today()
    fy_start_year, quarter = locate_fiscal(day, args.start_month)
    fy_start, fy_end = fiscal_year_range(fy_start_year, args.start_month)
    q_start = add_months(fy_start, 3 * (quarter - 1))
    q_end = add_months(fy_start, 3 * quarter) - timedelta(days=1)

    fy_number = fy_start_year if args.label == "start" else fy_end.year
    print("日期 %s → FY%d 第 %d 财季" % (day.isoformat(), fy_number, quarter))
    print("财年区间: %s ~ %s" % (fy_start.isoformat(), fy_end.isoformat()))
    print("本季区间: %s ~ %s" % (q_start.isoformat(), q_end.isoformat()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
