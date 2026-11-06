#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""历史日期星期查询：查询历史某年月日是星期几及距今多少年多少天。

用途：
    查询公元 1-9999 年任意日期是星期几（中英文），以及当年是否闰年、
    当年第几天、ISO 周号；并给出距基准日期（默认今天）的总相差天数、
    整周年数与下一个整周年纪念日。

用法：
    python birthday-weekday.py <日期YYYY-MM-DD> [--at YYYY-MM-DD]

示例命令：
    python birthday-weekday.py 2008-08-08
    python birthday-weekday.py 1949-10-01 --at 2026-11-02

说明：
    计算基于 Python 标准库 datetime（前推格里高利历，proleptic
    Gregorian）。早于 1582-10-15 的日期历史上多行儒略历，输出会附加
    对应提示。仅使用 Python 标准库；退出码：0 成功，2 参数/日期错误。
"""

import argparse
import calendar
import sys
from datetime import date

WEEK_CN = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
WEEK_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
GREGORIAN_START = date(1582, 10, 15)  # 格里高利历推行首日


def week_cn(d):
    return WEEK_CN[d.weekday()]


def full_years(ev, ref):
    y = ref.year - ev.year
    try:
        ann = ev.replace(year=ref.year)
    except ValueError:
        ann = date(ref.year, 2, 28)
    if ann > ref:
        y -= 1
    return max(y, 0)


def next_anniversary(ev, ref):
    """下一个（>= ref）整周年纪念日，返回 (date, 是否使用了2月28日替补)。"""
    for y in (ref.year, ref.year + 1):
        try:
            cand = ev.replace(year=y)
            fallback = False
        except ValueError:
            cand = date(y, 2, 28)
            fallback = True
        if cand >= ref:
            return cand, fallback
    raise AssertionError("unreachable")


def run(ev, ref, at_default):
    total = (ref - ev).days
    doy = (ev - date(ev.year, 1, 1)).days + 1
    diy = 366 if calendar.isleap(ev.year) else 365
    iso_week = ev.isocalendar()[1]
    leap = "闰年" if calendar.isleap(ev.year) else "平年"

    print(f"查询日期：{ev.isoformat()}")
    print(f"  星期：{week_cn(ev)}（英文 {WEEK_EN[ev.weekday()]}）")
    print(f"  当年：{ev.year} 年（{leap}），第 {doy} 天 / 共 {diy} 天，ISO 周号第 {iso_week} 周")
    if ev < GREGORIAN_START:
        print("  注：该日期早于格里高利历推行（1582-10-15），以上星期按前推格里高利历"
              "计算，与当时实行的儒略历日期对应关系可能不同。")
    print(f"基准日期：{ref.isoformat()}（{week_cn(ref)}）" + ("（默认今天）" if at_default else ""))
    if total == 0:
        print("距今：查询日期即基准日期（相差 0 天）")
        return
    if total > 0:
        print(f"距今：已 {total} 天")
        y = full_years(ev, ref)
        na, fb = next_anniversary(ev, ref)
        tip = "（2月29日事件，非闰年按2月28日）" if fb else ""
        print(f"  整周年：已满 {y} 周年；下一个整周年 {na.isoformat()}（{week_cn(na)}），"
              f"还有 {(na - ref).days} 天{tip}")
    else:
        print(f"距今：该日期在未来，距今还有 {-total} 天")


def parse_date(s):
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        raise argparse.ArgumentTypeError(f"日期格式应为 YYYY-MM-DD，收到：{s!r}")


def _utf8_stdio():
    """在非 UTF-8 控制台/管道下尽量以 UTF-8 输出。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (stream.encoding or "").lower().replace("-", "")
            if enc and enc != "utf8" and hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv=None):
    _utf8_stdio()
    p = argparse.ArgumentParser(
        prog="birthday-weekday.py",
        description="历史日期星期查询：星期几及距今多少年多少天。")
    p.add_argument("day", type=parse_date, metavar="YYYY-MM-DD", help="要查询的日期")
    p.add_argument("--at", type=parse_date, metavar="YYYY-MM-DD", default=None,
                   help="基准日期，默认今天")
    args = p.parse_args(argv)
    ref = args.at or date.today()
    try:
        run(args.day, ref, args.at is None)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
