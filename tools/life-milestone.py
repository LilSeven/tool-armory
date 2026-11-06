#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""里程碑时刻计算：给定出生日期/时刻，计算第 10000 天、第 10 亿秒等
里程碑的精确日期时间，并给出倒计时或已过去多久。

约定:
    「第 N 天」 = 出生日期算第 1 天，之后第 N-1 天的那天 00:00:00；
    「第 N 周」 = 出生日期之后第 (N-1)*7 天的那天 00:00:00；
    「第 N 小时/秒」 = 出生时刻 + N 小时/秒（活满 N 小时/秒的那一刻）。

用法:
    python life-milestone.py --birth 1990-06-15
    python life-milestone.py --birth "1990-06-15 08:30" --at "2026-11-02 12:00:00"
    python life-milestone.py --birth 1990-06-15 --days 30000 --seconds 2e9
"""

import argparse
import datetime as dt
import sys

DAY = dt.timedelta(days=1)


def _force_utf8():
    """让中文在管道/重定向（Windows 默认 GBK）下也不乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_when(text, what):
    text = text.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        "%s 无法解析: %r（示例 1990-06-15 或 \"1990-06-15 08:30\"）" % (what, text))


def fmt_num(x):
    """2e9 -> “20 亿”；10000 -> “10,000”；1.5e9 -> “1.5e+09”。"""
    if float(x).is_integer():
        n = int(x)
        if n >= 100000000 and n % 100000000 == 0:
            return "%d 亿" % (n // 100000000)
        return "{:,}".format(n)
    return "%g" % x


def humanize(sec):
    """秒数 -> “N 天 N 小时 N 分”之类的可读时长。"""
    sec = max(0, int(round(sec)))
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d >= 1:
        return "%d 天 %d 小时 %d 分" % (d, h, m)
    if h >= 1:
        return "%d 小时 %d 分 %d 秒" % (h, m, s)
    if m >= 1:
        return "%d 分 %d 秒" % (m, s)
    return "%d 秒" % s


def build_milestones(birth, extras):
    """返回 [(标签, 精确时刻), ...]，按时间排序。extras 为 (kind, n) 列表。"""
    midnight = dt.datetime.combine(birth.date(), dt.time())
    items = []
    for n in (5000, 10000, 15000, 20000, 25000, 30000):
        items.append(("第 %s 天" % fmt_num(n), midnight + (n - 1) * DAY))
    items.append(("第 1,000 周", midnight + 999 * 7 * DAY))
    items.append(("第 100,000 小时", birth + dt.timedelta(hours=100000)))
    for n in (5e8, 1e9, 2e9, 3e9):
        items.append(("第 %s 秒" % fmt_num(n), birth + dt.timedelta(seconds=n)))
    for kind, n in extras:
        if kind == "day":
            items.append(("自定义 第 %s 天" % fmt_num(n), midnight + (n - 1) * DAY))
        elif kind == "week":
            items.append(("自定义 第 %s 周" % fmt_num(n), midnight + (n - 1) * 7 * DAY))
        elif kind == "hour":
            items.append(("自定义 第 %s 小时" % fmt_num(n), birth + dt.timedelta(hours=n)))
        else:
            items.append(("自定义 第 %s 秒" % fmt_num(n), birth + dt.timedelta(seconds=n)))
    items.sort(key=lambda it: it[1])
    return items


def main(argv=None):
    _force_utf8()
    p = argparse.ArgumentParser(description="计算人生里程碑日期并倒计时")
    p.add_argument("--birth", required=True,
                   type=lambda s: parse_when(s, "出生时间"),
                   help="出生日期/时刻，如 1990-06-15 或 \"1990-06-15 08:30\"")
    p.add_argument("--at", type=lambda s: parse_when(s, "基准时间"),
                   help="以该时刻为“现在”来算（默认取当前时间）")
    p.add_argument("--days", type=float, action="append", default=[],
                   help="附加里程碑：第 N 天（可重复）")
    p.add_argument("--weeks", type=float, action="append", default=[],
                   help="附加里程碑：第 N 周（可重复）")
    p.add_argument("--hours", type=float, action="append", default=[],
                   help="附加里程碑：第 N 小时（可重复）")
    p.add_argument("--seconds", type=float, action="append", default=[],
                   help="附加里程碑：第 N 秒（可重复，如 2e9）")
    args = p.parse_args(argv)
    now = args.at or dt.datetime.now()
    extras = ([("day", n) for n in args.days] +
              [("week", n) for n in args.weeks] +
              [("hour", n) for n in args.hours] +
              [("second", n) for n in args.seconds])
    items = build_milestones(args.birth, extras)

    print("出生时刻：%s" % args.birth.strftime("%Y-%m-%d %H:%M:%S"))
    print("基准时刻：%s%s" % (now.strftime("%Y-%m-%d %H:%M:%S"),
                             "" if args.at else "（当前时间）"))
    if now >= args.birth:
        print("年龄约　 ：%.2f 岁" %
              ((now - args.birth).total_seconds() / 86400.0 / 365.2425))
    print("-" * 78)
    print("%-16s %-20s %-6s %s" % ("里程碑", "精确时刻", "状态", "距今"))
    for label, target in items:
        delta = (target - now).total_seconds()
        if delta >= 0:
            status, desc = "未到", "还有 " + humanize(delta)
        else:
            status, desc = "已过", "过去了 " + humanize(-delta)
        print("%-16s %-20s %-6s %s" %
              (label, target.strftime("%Y-%m-%d %H:%M:%S"), status, desc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
