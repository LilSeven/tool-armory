#!/usr/bin/env python3
"""终端月历渲染 —— 渲染指定月份的月历, 高亮今天与指定日期。

用法:
  python calendar-month.py                        # 当前月
  python calendar-month.py 2026 1                 # 指定年月
  python calendar-month.py 2026 1 --start sun     # 周日为一周起点(默认周一)
  python calendar-month.py 2026 1 --lang en       # 英文星期头(默认中文)
  python calendar-month.py 2026 1 --highlight 2026-01-01,2026-01-24
  python calendar-month.py 2026 1 --plain         # 禁用 ANSI 颜色, 高亮改用 * 前缀

高亮规则: 今天落在该月则高亮今天, --highlight 指定的日期也高亮。
支持 ANSI 的终端用反显标记, 否则(输出到管道或 --plain)在日期后加 *, 如 5*、15*。
"""

import argparse
import calendar as _cal
import re
import sys
import unicodedata
from datetime import date

GRID_W = 21  # 月历网格宽度: 7 天 * 每格 3 显示列
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
CN_WEEKDAYS = "一二三四五六日"  # 下标按 date.weekday(): 0=周一
EN_WEEKDAYS = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")
EN_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December")


def dw(s):
    """显示宽度: 先剔除 ANSI 转义序列, 全角字符按 2 列计。"""
    s = ANSI_RE.sub("", s)
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def pad_center(s, w):
    gap = max(0, w - dw(s))
    left = gap // 2
    return " " * left + s + " " * (gap - left)


def month_grid(year, month, start):
    """返回 6 行 x 7 列的 date/None 网格; start=0 一周从周一开始, 6 从周日。"""
    first = date(year, month, 1)
    ndim = _cal.monthrange(year, month)[1]
    lead = (first.weekday() - start) % 7
    cells = [None] * lead + [date(year, month, d) for d in range(1, ndim + 1)]
    while len(cells) % 7:
        cells.append(None)
    rows = [cells[i:i + 7] for i in range(0, len(cells), 7)]
    while len(rows) < 6:
        rows.append([None] * 7)
    return rows


def render_cell(d, marked, color):
    if d is None:
        return "   "
    body = f"{d.day:>2}"
    if d in marked:
        return ("\x1b[7m" + body + "\x1b[0m ") if color else (body + "*")
    return body + " "


def render_month_lines(year, month, start, lang, marked, color):
    lines = [pad_center(f"{year}年{month}月" if lang == "cn"
                        else f"{EN_MONTHS[month - 1]} {year}", GRID_W)]
    names = list(CN_WEEKDAYS) if lang == "cn" else list(EN_WEEKDAYS)
    order = [(start + i) % 7 for i in range(7)]
    lines.append("".join(f"{names[i]} " for i in order).rstrip())
    for row in month_grid(year, month, start):
        lines.append("".join(render_cell(d, marked, color) for d in row).rstrip())
    return lines


def parse_highlight(spec, ap):
    dates = set()
    for token in (spec or "").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            dates.add(date.fromisoformat(token))
        except ValueError:
            ap.error(f"无效日期 {token!r}, 应为 YYYY-MM-DD")
    return dates


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="渲染指定月份月历, 高亮今天")
    ap.add_argument("year", nargs="?", type=int, help="年(如 2026), 默认当前年")
    ap.add_argument("month", nargs="?", type=int, choices=range(1, 13),
                    help="月 1-12, 默认当前月")
    ap.add_argument("--start", choices=("mon", "sun"), default="mon",
                    help="一周起始日, 默认 mon")
    ap.add_argument("--lang", choices=("cn", "en"), default="cn",
                    help="星期表头语言, 默认 cn")
    ap.add_argument("--highlight", default="",
                    help="额外高亮日期, 逗号分隔, 如 2026-01-01,2026-01-24")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--color", action="store_true", help="强制使用 ANSI 反显高亮")
    grp.add_argument("--plain", action="store_true", help="禁用 ANSI, 用 * 后缀标记")
    args = ap.parse_args()

    if (args.year is None) != (args.month is None):
        ap.error("年 与 月 需同时提供, 或都不提供(渲染当前月)")
    today = date.today()
    if args.year is None:
        year, month = today.year, today.month
    else:
        year, month = args.year, args.month
    try:
        date(year, month, 1)
    except ValueError:
        ap.error(f"无效年月: {year}-{month}")

    marked = parse_highlight(args.highlight, ap)
    if today.year == year and today.month == month:
        marked.add(today)
    color = (not args.plain) and (args.color or sys.stdout.isatty())

    for line in render_month_lines(year, month,
                                   0 if args.start == "mon" else 6,
                                   args.lang, marked, color):
        print(line)
    if marked:
        print(f"[高亮 {len(marked)} 天: "
              f"{'反显' if color else '*'} 标记 = 今天或指定日期]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
