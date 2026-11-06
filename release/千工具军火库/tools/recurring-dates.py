#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""周期日期序列生成（recurring-dates）。

按规则生成日期序列：每 N 天 / 每 N 周的指定星期几 / 每 N 月的指定几号，
可设结束条件（--count 次数 或 --until 截止日期；两者可同时给出，先到先停）。

用法:
    python recurring-dates.py --start 2026-01-01 --every 14d --count 6
    python recurring-dates.py --start 2026-01-05 --every 1w --weekdays mon,wed --until 2026-02-28
    python recurring-dates.py --start 2026-01-31 --every 1m --count 6
    python recurring-dates.py --start 2026-02-01 --every 1m --monthday 1,15,-1 --count 6

规则说明:
    --every SPEC     Nd / Nw / Nm：每 N 天 / 周 / 月（N 为正整数，缺省 1d）
    --weekdays LIST  每 N 周内要取的星期几（逗号分隔，如 mon,wed），
                     仅配合 Nw 使用；缺省取 --start 当天的星期几
    --monthday LIST  每 N 月内要取的几号（逗号分隔；可为负：-1=月末，
                     -2=倒数第 2 天），仅配合 Nm 使用；缺省取 --start 的“几号”。
                     某月没有该日时自动取当月最后一天（如 31 在 2 月取 28/29）
    --count N        最多输出 N 个日期（正整数）
    --until DATE     只输出 <= 该日期的结果（含当天）

示例输出:
    $ python recurring-dates.py --start 2026-01-31 --every 1m --count 4
    2026-01-31
    2026-02-28
    2026-03-31
    2026-04-30

输出: 每行一个 ISO 日期（YYYY-MM-DD），按日期升序。
日期格式支持 YYYY-MM-DD / YYYY/MM/DD / YYYYMMDD。
缺结束条件、规则组合非法等参数错误退出码为 2。

仅使用 Python 标准库。
"""

from __future__ import annotations

import argparse
import calendar
import re
import sys
from datetime import date, datetime, timedelta

EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

WD = {
    "mon": 0, "monday": 0, "一": 0, "周一": 0, "星期一": 0,
    "tue": 1, "tuesday": 1, "二": 1, "周二": 1, "星期二": 1,
    "wed": 2, "wednesday": 2, "三": 2, "周三": 2, "星期三": 2,
    "thu": 3, "thursday": 3, "四": 3, "周四": 3, "星期四": 3,
    "fri": 4, "friday": 4, "五": 4, "周五": 4, "星期五": 4,
    "sat": 5, "saturday": 5, "六": 5, "周六": 5, "星期六": 5,
    "sun": 6, "sunday": 6, "日": 6, "天": 6, "周日": 6, "星期日": 6, "周天": 6, "星期天": 6,
}

WEEK_CAP = 5200    # 周步长安全上限（约百年量级），防止极端参数下无限循环
MONTH_CAP = 1200   # 月步长安全上限


def parse_date(s: str) -> date:
    t = s.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(
        f"无法解析日期: {s!r}（支持 YYYY-MM-DD / YYYY/MM/DD / YYYYMMDD）")


def parse_weekday(s: str) -> int:
    t = s.strip().lower()
    if t in WD:
        return WD[t]
    if re.fullmatch(r"[0-6]", t):
        return int(t)
    raise argparse.ArgumentTypeError(
        f"无法识别的星期几: {s!r}（可用 mon..sun、0-6（0=周一）或汉字 一/…/日）")


def parse_every(s: str):
    m = re.fullmatch(r"(\d+)([dwm])", s.strip().lower())
    if not m or int(m.group(1)) < 1:
        raise argparse.ArgumentTypeError(
            f"非法 --every: {s!r}（应为 Nd / Nw / Nm，N 为正整数）")
    return int(m.group(1)), m.group(2)


def parse_weekdays(s: str) -> list:
    out = set()
    for part in s.split(","):
        if part.strip():
            out.add(parse_weekday(part))
    if not out:
        raise argparse.ArgumentTypeError("星期几列表为空")
    return sorted(out)


def parse_monthday(s: str) -> list:
    out = set()
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            v = int(part)
        except ValueError:
            raise argparse.ArgumentTypeError(f"非法“几号”: {part!r}")
        if not -31 <= v <= 31 or v == 0:
            raise argparse.ArgumentTypeError(
                f"“几号”超出范围: {part}（应为 1..31 或 -1..-31，0 无意义）")
        out.add(v)
    if not out:
        raise argparse.ArgumentTypeError("几号列表为空")
    return sorted(out)


def add_months(y: int, m: int, k: int):
    t = (m - 1) + k
    return y + t // 12, t % 12 + 1


def gen_every_days(start: date, n: int, limit: int, until):
    d = start
    emitted = 0
    while emitted < limit:
        if until is not None and d > until:
            return
        yield d
        emitted += 1
        d += timedelta(days=n)


def gen_every_weeks(start: date, n: int, weekdays: list, limit: int, until):
    monday = start - timedelta(days=start.weekday())
    emitted = 0
    k = 0
    while emitted < limit and k <= WEEK_CAP:
        base = monday + timedelta(days=7 * n * k)
        for wd in weekdays:
            d = base + timedelta(days=wd)
            if d < start:
                continue
            if until is not None and d > until:
                return
            if emitted >= limit:
                return
            yield d
            emitted += 1
        k += 1
    if emitted < limit and k > WEEK_CAP:
        print("警告: 已达周步长安全上限，序列提前结束", file=sys.stderr)


def gen_every_months(start: date, n: int, monthdays: list, limit: int, until):
    emitted = 0
    k = 0
    while emitted < limit and k <= MONTH_CAP:
        y, m = add_months(start.year, start.month, n * k)
        ml = calendar.monthrange(y, m)[1]
        cands = set()
        for md in monthdays:
            if md > 0:
                cands.add(date(y, m, min(md, ml)))
            else:
                day = ml + 1 + md
                if day >= 1:
                    cands.add(date(y, m, day))
        for d in sorted(cands):
            if d < start:
                continue
            if until is not None and d > until:
                return
            if emitted >= limit:
                return
            yield d
            emitted += 1
        k += 1
    if emitted < limit and k > MONTH_CAP:
        print("警告: 已达月步长安全上限，序列提前结束", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="recurring-dates",
        description="按“每 N 天 / 每周几 / 每月几号”规则生成日期序列，可设结束条件。",
    )
    p.add_argument("--start", type=parse_date, required=True,
                   help="起始日期（含），如 2026-01-01")
    p.add_argument("--every", default="1d", type=parse_every,
                   help="步长: Nd / Nw / Nm（缺省 1d）")
    p.add_argument("--weekdays", type=parse_weekdays, metavar="LIST",
                   help="配合 Nw：星期几列表，如 mon,wed（缺省取 start 的星期几）")
    p.add_argument("--monthday", type=parse_monthday, metavar="LIST",
                   help="配合 Nm：几号列表，如 1,15,-1（缺省取 start 的几号）")
    p.add_argument("--count", type=int, help="最多输出 N 个日期")
    p.add_argument("--until", type=parse_date, help="截止日期（含）")
    return p


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args = build_parser().parse_args(argv)

    n, unit = args.every
    if args.weekdays is not None and unit != "w":
        print("错误: --weekdays 仅配合 --every Nw 使用", file=sys.stderr)
        return 2
    if args.monthday is not None and unit != "m":
        print("错误: --monthday 仅配合 --every Nm 使用", file=sys.stderr)
        return 2
    if args.count is None and args.until is None:
        print("错误: 必须提供 --count 或 --until 之一作为结束条件", file=sys.stderr)
        return 2
    if args.count is not None and args.count < 1:
        print(f"错误: --count 应为正整数，收到 {args.count}", file=sys.stderr)
        return 2

    limit = args.count if args.count is not None else 10 ** 9
    if unit == "d":
        gen = gen_every_days(args.start, n, limit, args.until)
    elif unit == "w":
        weekdays = args.weekdays if args.weekdays is not None else [args.start.weekday()]
        gen = gen_every_weeks(args.start, n, weekdays, limit, args.until)
    else:
        monthdays = args.monthday if args.monthday is not None else [args.start.day]
        gen = gen_every_months(args.start, n, monthdays, limit, args.until)

    for d in gen:
        print(d.isoformat())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
