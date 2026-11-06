#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""月末星期几计算（last-weekday）。

求某月最后一个指定星期几的日期（如 2026 年 11 月最后一个周四），也支持
按“倒数第 n 个”取（--from-end 2 = 倒数第 2 个）；并可输出当月各星期几
的分布（Mon..Sun 各出现几次，可看出哪些星期几在该月出现 5 次）。
支持批量多月份。

用法:
    python last-weekday.py YEAR [WEEKDAY] [-m 11 | 1-12] [--from-end N] [--all] [--dist] [-v]

示例命令:
    python last-weekday.py 2026 thu -m 11
    python last-weekday.py 2026 fri -m 1-12
    python last-weekday.py 2026 fri -m 5 --from-end 2 -v
    python last-weekday.py 2026 -m 2 --all
    python last-weekday.py 2026 -m 5 --dist

输出:
    指定 WEEKDAY 时   每行一个 ISO 日期（YYYY-MM-DD）；-v 附说明
    --all             每月一行: 2026-11 Mon=2026-11-30 Tue=...
    --dist            每月一行: 2026-11 Mon=5 Tue=4 ... Sun=5

WEEKDAY 写法: mon..sun / 0-6（0=周一）/ 汉字 一二三四五六日天。
WEEKDAY、--all、--dist 至少提供其一，否则报错（退出码 2）。

仅使用 Python 标准库。
"""

from __future__ import annotations

import argparse
import calendar
import re
import sys
from datetime import date, timedelta

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


def parse_weekday(s: str) -> int:
    t = s.strip().lower()
    if t in WD:
        return WD[t]
    if re.fullmatch(r"[0-6]", t):
        return int(t)
    raise argparse.ArgumentTypeError(
        f"无法识别的星期几: {s!r}（可用 mon..sun、0-6（0=周一）或汉字 一/…/日）")


def parse_months(s: str) -> list:
    months = set()
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if part.lower() in ("all", "全年"):
            months.update(range(1, 13))
            continue
        m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if not (1 <= a <= 12 and 1 <= b <= 12) or a > b:
                raise argparse.ArgumentTypeError(f"非法月份区间: {part}")
            months.update(range(a, b + 1))
        elif part.isdigit() and 1 <= int(part) <= 12:
            months.add(int(part))
        else:
            raise argparse.ArgumentTypeError(f"非法月份: {part}")
    if not months:
        raise argparse.ArgumentTypeError("月份列表为空")
    return sorted(months)


def last_weekday_of_month(year: int, month: int, wd: int, from_end: int = 1):
    """返回该月倒数第 from_end 个 wd 星期几的 date；不存在（越出当月）返回 None。"""
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    d = d - timedelta(days=(d.weekday() - wd) % 7)      # 最后一个
    d = d - timedelta(days=7 * (from_end - 1))          # 再往回 from_end-1 个
    return d if (d.year == year and d.month == month) else None


def month_weekday_counts(year: int, month: int) -> list:
    days = calendar.monthrange(year, month)[1]
    counts = [0] * 7
    for day in range(1, days + 1):
        counts[date(year, month, day).weekday()] += 1
    return counts


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="last-weekday",
        description="求某月最后一个（或倒数第 n 个）星期几，并可输出当月各星期几分布。",
    )
    p.add_argument("year", type=int, help="年份，如 2026")
    p.add_argument("weekday", nargs="?", type=parse_weekday, default=None,
                   help="星期几：mon..sun / 0-6（0=周一）/ 汉字 一..日")
    p.add_argument("-m", "--months", default="1-12", type=parse_months,
                   help="月份列表，如 11 或 1-12（缺省全年）")
    p.add_argument("--from-end", type=int, default=1, metavar="N",
                   help="倒数第 N 个（N>=1，缺省 1 即最后一个），仅配合 WEEKDAY 使用")
    p.add_argument("--all", action="store_true",
                   help="输出每月 Mon..Sun 全部 7 个“最后一个”日期")
    p.add_argument("--dist", action="store_true",
                   help="输出每月各星期几出现次数的分布")
    p.add_argument("-v", "--verbose", action="store_true", help="输出附带说明列")
    return p


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args = build_parser().parse_args(argv)

    if not (1 <= args.year <= 9999):
        print(f"错误: 年份超出范围: {args.year}", file=sys.stderr)
        return 2
    if args.weekday is None and not (args.all or args.dist):
        print("错误: 需提供 WEEKDAY，或使用 --all / --dist 至少其一", file=sys.stderr)
        return 2
    if args.from_end < 1 or args.from_end > 52:
        print(f"错误: --from-end 应为 1..52，收到 {args.from_end}", file=sys.stderr)
        return 2

    ok = True
    if args.weekday is not None:
        for m in args.months:
            d = last_weekday_of_month(args.year, m, args.weekday, args.from_end)
            if d is None:
                print(f"提示: {args.year}-{m:02d} 不存在倒数第 {args.from_end} 个 "
                      f"{EN[args.weekday]}", file=sys.stderr)
                continue
            if args.verbose:
                tail = "" if args.from_end == 1 else f"（倒数第{args.from_end}个）"
                print(f"{d.isoformat()}  # {args.year}-{m:02d} 最后一个 "
                      f"{EN[args.weekday]}{tail}")
            else:
                print(d.isoformat())

    if args.all:
        for m in args.months:
            cells = []
            for wd in range(7):
                d = last_weekday_of_month(args.year, m, wd)
                cells.append(f"{EN[wd]}={d.isoformat()}" if d else f"{EN[wd]}=-")
            print(f"{args.year}-{m:02d}: " + " ".join(cells))

    if args.dist:
        for m in args.months:
            counts = month_weekday_counts(args.year, m)
            print(f"{args.year}-{m:02d}: " +
                  " ".join(f"{EN[i]}={c}" for i, c in enumerate(counts)))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
