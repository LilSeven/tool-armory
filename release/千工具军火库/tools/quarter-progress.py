#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""季度进度条：以进度条形式显示某日期所处自然季度与年度的已过时间百分比。

示例命令:
  python quarter-progress.py                       # 按今天显示
  python quarter-progress.py --date 2026-11-02
  python quarter-progress.py --date 2026-11-02 --width 40

说明:
  季度为自然季度（1-3 月为 Q1，依次类推）；"已过"含当天，百分比精确到日。
"""

import argparse
import sys
from datetime import date, timedelta

WEEKDAY_CN = ("一", "二", "三", "四", "五", "六", "日")


def parse_date(text):
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError("日期格式应为 YYYY-MM-DD，收到: %r" % text)


def quarter_range(year, quarter):
    """返回某年某自然季度的 (首日, 末日)，quarter 取 1-4。"""
    start = date(year, 3 * (quarter - 1) + 1, 1)
    if quarter == 4:
        return start, date(year, 12, 31)
    return start, date(year, 3 * quarter + 1, 1) - timedelta(days=1)


def render_bar(percent, width):
    percent = max(0.0, min(100.0, percent))
    filled = max(0, min(width, int(round(width * percent / 100.0))))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="quarter-progress.py",
        description="以进度条形式显示当前季度、年度已过时间百分比（精确到日）。",
    )
    parser.add_argument("--date", type=parse_date, default=None,
                        help="目标日期 YYYY-MM-DD（缺省为今天）")
    parser.add_argument("--width", type=int, default=30,
                        help="进度条字符宽度（缺省 30）")
    return parser


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.width < 3:
        parser.error("--width 至少为 3")

    day = args.date if args.date is not None else date.today()
    quarter = (day.month - 1) // 3 + 1
    q_start, q_end = quarter_range(day.year, quarter)
    q_total = (q_end - q_start).days + 1
    q_elapsed = (day - q_start).days + 1
    q_pct = q_elapsed * 100.0 / q_total

    y_start, y_end = date(day.year, 1, 1), date(day.year, 12, 31)
    y_total = (y_end - y_start).days + 1
    y_elapsed = (day - y_start).days + 1
    y_pct = y_elapsed * 100.0 / y_total

    print("%s（周%s）· %d 年第 %d 季度（Q%d）"
          % (day.isoformat(), WEEKDAY_CN[day.weekday()], day.year, quarter, quarter))
    print("季度: %s ~ %s，已过 %d/%d 天（%.1f%%）"
          % (q_start.isoformat(), q_end.isoformat(), q_elapsed, q_total, q_pct))
    print("     %s %.1f%%" % (render_bar(q_pct, args.width), q_pct))
    print("年度: %s ~ %s，已过 %d/%d 天（%.1f%%）"
          % (y_start.isoformat(), y_end.isoformat(), y_elapsed, y_total, y_pct))
    print("     %s %.1f%%" % (render_bar(y_pct, args.width), y_pct))
    return 0


if __name__ == "__main__":
    sys.exit(main())
