#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""财年进度显示：显示某日期在其财年内已过/剩余的日历天数与工作日（周一至周五）及百分比进度。

示例命令:
  # 财年从 4 月开始，看 2026-11-02 的财年进度
  python fiscal-progress.py --start-month 4 --date 2026-11-02

  # 自然财年（默认起始月 1），按今天
  python fiscal-progress.py

  # 自定义进度条宽度
  python fiscal-progress.py --start-month 4 --date 2026-11-02 --width 40

说明:
  "已过"含当天（即当天结束时刻的进度）；工作日按周一至周五计，
  不考虑法定节假日与调休。
"""

import argparse
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
    import calendar
    index = day.year * 12 + (day.month - 1) + months
    year, month0 = divmod(index, 12)
    month = month0 + 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last))


def fiscal_year_range(fy, start_month):
    """返回编号为 fy 的财年 (起, 止)，编号取财年开始的年份。"""
    start = date(fy, start_month, 1)
    end = add_months(start, 12) - timedelta(days=1)
    return start, end


def count_workdays(first, last):
    """闭区间 [first, last] 内周一至周五的天数。"""
    if last < first:
        return 0
    total = (last - first).days + 1
    weeks, remainder = divmod(total, 7)
    count = weeks * 5
    for i in range(remainder):
        if (first.weekday() + i) % 7 < 5:
            count += 1
    return count


def render_bar(percent, width):
    percent = max(0.0, min(100.0, percent))
    filled = max(0, min(width, int(round(width * percent / 100.0))))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="fiscal-progress.py",
        description="显示日期在财年内已过/剩余的日历天数与工作日百分比进度。",
    )
    parser.add_argument("--date", type=parse_date, default=None,
                        help="目标日期 YYYY-MM-DD（缺省为今天）")
    parser.add_argument("--start-month", type=parse_month, default=1,
                        help="财年起始月 1-12（缺省 1，即自然年）")
    parser.add_argument("--width", type=int, default=24,
                        help="进度条字符宽度（缺省 24）")
    return parser


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.width < 3:
        parser.error("--width 至少为 3")

    day = args.date if args.date is not None else date.today()
    fy = day.year if day.month >= args.start_month else day.year - 1
    fy_start, fy_end = fiscal_year_range(fy, args.start_month)

    total_days = (fy_end - fy_start).days + 1
    elapsed_days = (day - fy_start).days + 1
    remaining_days = total_days - elapsed_days
    total_work = count_workdays(fy_start, fy_end)
    elapsed_work = count_workdays(fy_start, day)
    remaining_work = count_workdays(day + timedelta(days=1), fy_end)

    day_pct = elapsed_days * 100.0 / total_days
    work_pct = (elapsed_work * 100.0 / total_work) if total_work else 0.0

    print("财年 FY%d: %s ~ %s（共 %d 天，其中工作日 %d 天）"
          % (fy, fy_start.isoformat(), fy_end.isoformat(), total_days, total_work))
    print("日历天数: 已过 %d/%d 天（%.1f%%），剩余 %d 天"
          % (elapsed_days, total_days, day_pct, remaining_days))
    print("工作日  : 已过 %d/%d 天（%.1f%%），剩余 %d 天"
          % (elapsed_work, total_work, work_pct, remaining_work))
    print("日历 %s %.1f%%" % (render_bar(day_pct, args.width), day_pct))
    print("工作 %s %.1f%%" % (render_bar(work_pct, args.width), work_pct))
    return 0


if __name__ == "__main__":
    sys.exit(main())
