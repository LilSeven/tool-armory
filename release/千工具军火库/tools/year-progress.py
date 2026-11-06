#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""年度进度显示：显示当前年度已过百分比的动态进度条，精确到日。

示例命令:
  python year-progress.py                          # 按今天显示
  python year-progress.py --date 2026-11-02
  python year-progress.py --date 2026-11-02 --width 40

说明:
  "已过"含当天（即第 N 天 / 共 M 天）；进度条随日期逐日推进，
  闰年自动按 366 天计。
"""

import argparse
import sys
from datetime import date

WEEKDAY_CN = ("一", "二", "三", "四", "五", "六", "日")


def parse_date(text):
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError("日期格式应为 YYYY-MM-DD，收到: %r" % text)


def render_bar(percent, width):
    percent = max(0.0, min(100.0, percent))
    filled = max(0, min(width, int(round(width * percent / 100.0))))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="year-progress.py",
        description="显示当前年度已过百分比的动态进度条，精确到日。",
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
    start, end = date(day.year, 1, 1), date(day.year, 12, 31)
    total = (end - start).days + 1
    elapsed = (day - start).days + 1
    remaining = total - elapsed
    percent = elapsed * 100.0 / total

    print("%s（周%s）· %d 年第 %d 天 / 共 %d 天"
          % (day.isoformat(), WEEKDAY_CN[day.weekday()], day.year, elapsed, total))
    print("已过 %.2f%%  %s" % (percent, render_bar(percent, args.width)))
    print("剩余 %d 天（约 %.1f 周），年末 %s"
          % (remaining, remaining / 7.0, end.isoformat()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
