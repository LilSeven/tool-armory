#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""所在周起止计算:计算日期所在周的起止日期,周起始日可配置为周一或周日。

示例命令:
  python week-range.py 2026-11-02               # 周一为一周之首(默认)
  python week-range.py 2026-11-02 --start sun   # 周日为一周之首
  python week-range.py 2026-11-02 --offset 1    # 平移到下一周
  python week-range.py                          # 缺省取今天
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


def week_bounds(d, start="mon"):
    """返回日期 d 所在周的 (周首, 周末),start 取 "mon"(周一)或 "sun"(周日)。"""
    offset = d.weekday() if start == "mon" else (d.weekday() + 1) % 7
    first = d - timedelta(days=offset)
    return first, first + timedelta(days=6)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        description="计算日期所在周的起止日期,周起始日可选周一或周日")
    parser.add_argument("date", nargs="?", help="日期(YYYY-MM-DD),缺省为今天")
    parser.add_argument("--start", choices=("mon", "sun"), default="mon",
                        help="周起始日:mon=周一(默认),sun=周日")
    parser.add_argument("--offset", type=int, default=0,
                        help="按周平移:-1 为上周,1 为下周(默认 0)")
    args = parser.parse_args(argv)
    d = parse_date(args.date) if args.date else date.today()
    d = d + timedelta(weeks=args.offset)
    first, last = week_bounds(d, args.start)
    start_cn = "周一" if args.start == "mon" else "周日"
    print("基准日期 %s(%s),周起始日:%s,平移 %d 周"
          % (d.isoformat(), WEEKDAY_CN[d.weekday()], start_cn, args.offset))
    print("所在周:%s(%s) 至 %s(%s),共 7 天"
          % (first.isoformat(), WEEKDAY_CN[first.weekday()],
             last.isoformat(), WEEKDAY_CN[last.weekday()]))
    if args.start == "mon":
        iy, iw, _ = first.isocalendar()
        print("该周为 ISO 8601 第 %d 年第 %d 周" % (iy, iw))
    else:
        print("注:ISO 8601 周号以周一为周首,周日起始的周没有对应的 ISO 周号")
    return 0


if __name__ == "__main__":
    sys.exit(main())
