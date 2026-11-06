#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""宝宝月龄计算：计算婴儿月龄天数，给出百天、周岁等关键日期。

用途：
    按出生日期和基准日期（默认今天）计算宝宝月龄（X个月Y天）、
    日龄（N天，M周D天）与下一次满月龄，并列出满月、百天、半岁、
    周岁、两周岁等关键日期（已过/今天/倒计时）。

用法：
    python baby-age.py <出生日期YYYY-MM-DD> [--at YYYY-MM-DD]

示例命令：
    python baby-age.py 2026-06-15
    python baby-age.py 2026-06-15 --at 2026-11-02

说明：
    - 月龄按"满整月"计算（1月31日出生 → 2月28日即满1个月）；
    - 百天按"出生后第100天"（出生日为第1天，即出生日+99天）；
    - 仅使用 Python 标准库；退出码：0 成功，2 参数/日期错误。
"""

import argparse
import calendar
import sys
from datetime import date, timedelta

WEEK_CN = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


def week_cn(d):
    return WEEK_CN[d.weekday()]


def add_months(d, n):
    total = d.year * 12 + (d.month - 1) + n
    y, m0 = divmod(total, 12)
    m = m0 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def full_months(ev, ref):
    m = (ref.year - ev.year) * 12 + (ref.month - ev.month)
    if m > 0 and add_months(ev, m) > ref:
        m -= 1
    return max(m, 0)


def run(birth, ref, at_default):
    if ref < birth:
        raise ValueError("基准日期早于出生日期")
    total = (ref - birth).days
    months = full_months(birth, ref)
    anchor = add_months(birth, months)
    rest = (ref - anchor).days

    print(f"出生日期：{birth.isoformat()}（{week_cn(birth)}）")
    print(f"基准日期：{ref.isoformat()}（{week_cn(ref)}）" + ("（默认今天）" if at_default else ""))
    print(f"月龄：{months} 个月 {rest} 天")
    print(f"日龄：{total} 天（{total // 7} 周 {total % 7} 天）")
    nxt = add_months(birth, months + 1)
    print(f"下一次满月龄：{months + 1} 个月 → {nxt.isoformat()}（{week_cn(nxt)}），"
          f"还有 {(nxt - ref).days} 天")

    milestones = [
        ("满月（1个月）", add_months(birth, 1)),
        ("百天（出生后第100天）", birth + timedelta(days=99)),
        ("半岁（6个月）", add_months(birth, 6)),
        ("周岁（12个月）", add_months(birth, 12)),
        ("两周岁（24个月）", add_months(birth, 24)),
    ]
    print("关键日期：")
    for name, d in milestones:
        if ref > d:
            status = f"已过 {(ref - d).days} 天"
        elif ref == d:
            status = "就是今天"
        else:
            status = f"还有 {(d - ref).days} 天"
        print(f"  {d.isoformat()}（{week_cn(d)}）  {name}  [{status}]")


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
        prog="baby-age.py",
        description="宝宝月龄计算：月龄天数与百天、周岁等关键日期。")
    p.add_argument("birth", type=parse_date, metavar="YYYY-MM-DD", help="出生日期")
    p.add_argument("--at", type=parse_date, metavar="YYYY-MM-DD", default=None,
                   help="基准日期，默认今天")
    args = p.parse_args(argv)
    ref = args.at or date.today()
    try:
        run(args.birth, ref, args.at is None)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
