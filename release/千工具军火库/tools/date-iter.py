#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日期区间遍历（date-iter）。

按天/周/月步长遍历闭区间 [START, END]，逐行输出日期；可选过滤周末
（--skip-weekend：周六周日不输出）。月步长锚定 START 的“几号”，
当月不足该日时取当月最后一天（如 1-31 -> 2-28 -> 3-31，无漂移）。

用法:
    python date-iter.py START END [--step day|week|month] [-n N] [--skip-weekend] [--with-weekday]

示例命令:
    python date-iter.py 2026-01-01 2026-01-10
    python date-iter.py 2026-01-01 2026-02-01 --step week -n 2 --with-weekday
    python date-iter.py 2026-01-31 2026-07-31 --step month
    python date-iter.py 2026-01-01 2026-01-11 --step day --skip-weekend

选项:
    --step day|week|month  步长单位（缺省 day）
    -n, --step-n N         步长倍数（N>=1，缺省 1，如 -n 2 = 每 2 周）
    --skip-weekend         跳过周六、周日（只影响输出，不影响步进）
    --with-weekday         行尾附加空格 + 三字母星期缩写（Mon..Sun）

输出: 每行一个 ISO 日期（YYYY-MM-DD），升序，含 START 与 END。
日期格式支持 YYYY-MM-DD / YYYY/MM/DD / YYYYMMDD。
START 晚于 END 或参数非法时报错，退出码 2。

仅使用 Python 标准库。
"""

from __future__ import annotations

import argparse
import calendar
import re
import sys
from datetime import date, datetime, timedelta

EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

MONTH_CAP = 12000  # 月步长安全上限（约一千年），防止异常参数失控


def parse_date(s: str) -> date:
    t = s.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(
        f"无法解析日期: {s!r}（支持 YYYY-MM-DD / YYYY/MM/DD / YYYYMMDD）")


def add_months(y: int, m: int, k: int):
    t = (m - 1) + k
    return y + t // 12, t % 12 + 1


def iter_step(start: date, end: date, step: str, n: int):
    if step in ("day", "week"):
        delta = timedelta(days=n) if step == "day" else timedelta(weeks=n)
        d = start
        while d <= end:
            yield d
            d += delta
    else:  # month
        k = 0
        while True:
            y, m = add_months(start.year, start.month, n * k)
            d = date(y, m, min(start.day, calendar.monthrange(y, m)[1]))
            if d > end or k > MONTH_CAP:
                return
            yield d
            k += 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="date-iter",
        description="按天/周/月步长遍历日期区间并逐行输出，可过滤周末。",
    )
    p.add_argument("start", type=parse_date, help="起始日期（含）")
    p.add_argument("end", type=parse_date, help="结束日期（含）")
    p.add_argument("--step", choices=("day", "week", "month"), default="day",
                   help="步长单位（缺省 day）")
    p.add_argument("-n", "--step-n", type=int, default=1, metavar="N",
                   help="步长倍数，N>=1（缺省 1）")
    p.add_argument("--skip-weekend", action="store_true",
                   help="跳过周六、周日（只影响输出，不影响步进）")
    p.add_argument("--with-weekday", action="store_true",
                   help="行尾附加三字母星期缩写（Mon..Sun）")
    return p


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args = build_parser().parse_args(argv)

    if args.start > args.end:
        print(f"错误: 起始日期晚于结束日期: {args.start} > {args.end}", file=sys.stderr)
        return 2
    if args.step_n < 1:
        print(f"错误: --step-n 应为正整数，收到 {args.step_n}", file=sys.stderr)
        return 2

    for d in iter_step(args.start, args.end, args.step, args.step_n):
        if args.skip_weekend and d.weekday() >= 5:
            continue
        if args.with_weekday:
            print(f"{d.isoformat()} {EN[d.weekday()]}")
        else:
            print(d.isoformat())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
