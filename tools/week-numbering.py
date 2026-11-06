#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""周编号体系对比:同一天在 ISO-8601、美国、简单周编号三种体系下的周号对照。

三种体系的规则:
  ISO-8601  周一为一周之首;包含当年第一个周四的那一周为第 1 周,
            年末年初的周可能归属上一年或下一年("周年"与公历年可不同)。
  US 美式   周日为一周之首;包含 1 月 1 日的那一周为第 1 周,
            跨年周(同时含 12 月底与次年 1 月 1 日)归入新年份。
  简单编号  1 月 1 日恒为第 1 周第 1 天,每 7 天进一周,首周可不足 7 天,不跨年。

示例命令:
  python week-numbering.py 2026-11-02
  python week-numbering.py 2026-01-01 2025-12-29
  python week-numbering.py                 # 不带参数则取今天
"""

import argparse
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


def us_week(d):
    """US 周编号:返回 (周年, 周号, 周内第几天),周日为每周第 1 天。"""

    def week1_sunday(year):
        # 该年 1 月 1 日所在周(以周日开头)的周日
        jan1 = date(year, 1, 1)
        return jan1 - timedelta(days=(jan1.weekday() + 1) % 7)

    year = d.year + 1 if d >= week1_sunday(d.year + 1) else d.year
    week = (d - week1_sunday(year)).days // 7 + 1
    day_in_week = (d.weekday() + 1) % 7 + 1  # 周日=1 ... 周六=7
    return year, week, day_in_week


def simple_week(d):
    """简单周编号:返回 (年, 周号, 周内第几天),以 1 月 1 日为第 1 周第 1 天。"""
    yday = d.timetuple().tm_yday
    return d.year, (yday - 1) // 7 + 1, (yday - 1) % 7 + 1


def show(d):
    """打印某天在三种体系下的周号对照表。"""
    iy, iw, iwd = d.isocalendar()
    uy, uw, uwd = us_week(d)
    sy, sw, swd = simple_week(d)
    print("日期 %s(%s)" % (d.isoformat(), WEEKDAY_CN[d.weekday()]))
    print("  体系      周年    周号     周内第几天  周首规则")
    for name, y, w, wd, rule in (
        ("ISO-8601", iy, iw, iwd, "周一为首;含当年第一个周四的周为第 1 周"),
        ("US 美式", uy, uw, uwd, "周日为首;含 1 月 1 日的周为第 1 周,跨年周归新年"),
        ("简单编号", sy, sw, swd, "1 月 1 日恒为第 1 周第 1 天,每 7 天进一周"),
    ):
        print("  %-8s %d    第%2d周   第%d天        %s" % (name, y, w, wd, rule))
    print()


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        description="同一天在 ISO-8601、美国、简单周编号三种体系下的周号对照")
    parser.add_argument("dates", nargs="*",
                        help="日期(YYYY-MM-DD),可给多个;缺省为今天")
    args = parser.parse_args(argv)
    days = [parse_date(s) for s in args.dates] if args.dates else [date.today()]
    for d in days:
        show(d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
