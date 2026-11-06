#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工作日历矩阵 —— 在终端渲染指定月份的日历网格，用符号标记节假日(*)、
补班日(+)与周末(-)，底部统计该月工作日/休假日天数；支持 ANSI 颜色。

用法:
    python workday-grid.py 2027-02
    python workday-grid.py 2027-02 --holiday 02-15,02-16..02-17 --workday 02-20,02-27
    python workday-grid.py 2027-10 --holiday 10-01..10-07 --color

日期格式:
    --holiday / --workday 可重复或逗号分隔，每项为 MM-DD、YYYY-MM-DD 或
    A..B 区间（含两端）；不属于渲染月份的日期会被忽略并在 stderr 提示。
    MM-DD 按被渲染月份的年份解释。同一日期同时是节假日与补班日时，补班优先。

示例输出:
    $ python workday-grid.py 2027-02 --holiday 02-15..02-17 --workday 02-20
    2027年02月  工作日 18 天 · 休 10 天 (共 28 天)
     一  二  三  四  五  六  日
      1   2   3   4   5   6-  7-
      8   9  10  11  12  13- 14-
     15* 16* 17* 18  19  20+ 21-
     22  23  24  25  26  27- 28-
    图例: * 节假日  + 补班(调休上班)  - 周末  空白=工作日

退出码: 0 成功; 2 参数或日期格式错误。
仅用 Python 标准库，单文件。
"""

from __future__ import annotations

import argparse
import calendar
import re
import sys
from datetime import date, timedelta

COLORS = {"*": "31", "+": "36", "-": "90"}  # 红/青/暗灰


def _setup_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def parse_month(text: str):
    """解析 YYYY-MM，返回 (year, month)，失败抛 ValueError。"""
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", text.strip())
    if not m:
        raise ValueError(f"月份格式应为 YYYY-MM: {text!r}")
    year, month = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"月份超出 1-12: {month}")
    return year, month


def expand_dates(specs, year) -> set:
    """把 MM-DD / YYYY-MM-DD / A..B（可逗号分隔）展开成 date 集合。"""
    def one(t: str) -> date:
        parts = t.strip().split("-")
        if len(parts) == 2:
            try:
                return date(year, int(parts[0]), int(parts[1]))
            except ValueError:
                raise ValueError(f"无效日期: {t}") from None
        try:
            return date.fromisoformat(t.strip())
        except ValueError:
            raise ValueError(f"无效日期: {t}") from None

    out = set()
    for item in specs:
        for piece in str(item).split(","):
            piece = piece.strip()
            if not piece:
                continue
            if ".." in piece:
                a, _, b = piece.partition("..")
                d1, d2 = one(a), one(b)
                if d2 < d1:
                    raise ValueError(f"日期区间倒序: {piece}")
                if (d2 - d1).days > 400:
                    raise ValueError(f"日期区间过长(>400 天): {piece}")
                cur = d1
                while cur <= d2:
                    out.add(cur)
                    cur += timedelta(days=1)
            else:
                out.add(one(piece))
    return out


def clip_to_month(dates: set, year: int, month: int, label: str) -> set:
    """只保留渲染月份内的日期，其余打到 stderr 提示。"""
    extra = sorted(d for d in dates if (d.year, d.month) != (year, month))
    if extra:
        print(f"注意: 忽略不属于 {year}-{month:02d} 的{label}: "
              + "，".join(d.isoformat() for d in extra), file=sys.stderr)
    return {d for d in dates if (d.year, d.month) == (year, month)}


def mark_of(d: date, holidays: set, workdays: set) -> str:
    if d in workdays:
        return "+"
    if d in holidays:
        return "*"
    if d.weekday() >= 5:
        return "-"
    return " "


def month_stats(year: int, month: int, holidays: set, workdays: set):
    ndays = calendar.monthrange(year, month)[1]
    work = 0
    for dd in range(1, ndays + 1):
        d = date(year, month, dd)
        if d in workdays or (d.weekday() < 5 and d not in holidays):
            work += 1
    return ndays, work, ndays - work


def render(year: int, month: int, holidays: set, workdays: set, color: bool) -> str:
    ndays, work, off = month_stats(year, month, holidays, workdays)
    lines = [f"{year}年{month:02d}月  工作日 {work} 天 · 休 {off} 天 (共 {ndays} 天)",
             "".join(f" {h} " for h in "一二三四五六日").rstrip()]
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(year, month):
        cells = []
        for dd in week:
            if dd == 0:
                cells.append("    ")
                continue
            d = date(year, month, dd)
            mk = mark_of(d, holidays, workdays)
            cell = f"{dd:>3}{mk}"
            if color and mk in COLORS:
                cell = f"\x1b[{COLORS[mk]}m{cell}\x1b[0m"
            cells.append(cell)
        lines.append("".join(cells).rstrip())
    lines.append("图例: * 节假日  + 补班(调休上班)  - 周末  空白=工作日")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="终端渲染指定月份日历，标记节假日、补班日与周末")
    parser.add_argument("month", help="要渲染的月份，格式 YYYY-MM")
    parser.add_argument("--holiday", action="append", default=[], metavar="D",
                        help="节假日日期 MM-DD / YYYY-MM-DD / A..B，可重复或逗号分隔")
    parser.add_argument("--workday", action="append", default=[], metavar="D",
                        help="补班日（周末调休上班）日期，格式同 --holiday")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--color", action="store_true", help="强制使用 ANSI 颜色")
    group.add_argument("--no-color", action="store_true", help="禁用 ANSI 颜色")
    args = parser.parse_args(argv)

    try:
        year, month = parse_month(args.month)
        holidays = clip_to_month(expand_dates(args.holiday, year), year, month, "节假日")
        workdays = clip_to_month(expand_dates(args.workday, year), year, month, "补班日")
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    color = True if args.color else (False if args.no_color else sys.stdout.isatty())
    print(render(year, month, holidays, workdays, color))
    return 0


if __name__ == "__main__":
    _setup_stdio()
    sys.exit(main())
