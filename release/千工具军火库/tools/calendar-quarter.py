#!/usr/bin/env python3
"""季度三月并历 —— 把某季度三个月份并排渲染在同一屏, 便于对照。

用法:
  python calendar-quarter.py                    # 当前季度
  python calendar-quarter.py 2026 3             # 2026 年第 3 季度(7-9月)
  python calendar-quarter.py 2026 1 --start sun --lang en
  python calendar-quarter.py 2026 4 --highlight 2026-12-25,2026-12-31 --plain

高亮规则: --highlight 指定的日期高亮, 今天落在该季度内也高亮。
支持 ANSI 的终端用反显标记, 否则(输出到管道或 --plain)在日期后加 *, 如 5*、15*。
"""

import argparse
import calendar as _cal
import re
import sys
import unicodedata
from datetime import date

GRID_W = 21  # 单月网格宽度: 7 天 * 每格 3 显示列
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


def pad_r(s, w):
    return s + " " * max(0, w - dw(s))


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


def render_block(year, month, start, lang, marked, color):
    """单月块共 8 行: 月标题 + 星期头 + 6 行日期。"""
    lines = [pad_center(f"{month}月" if lang == "cn" else EN_MONTHS[month - 1], GRID_W)]
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
    ap = argparse.ArgumentParser(description="把某季度三个月份并排渲染在同一屏")
    ap.add_argument("year", nargs="?", type=int, help="年份(如 2026), 默认当前年")
    ap.add_argument("quarter", nargs="?", type=int, help="季度 1-4, 默认当前季度")
    ap.add_argument("--start", choices=("mon", "sun"), default="mon",
                    help="一周起始日, 默认 mon")
    ap.add_argument("--lang", choices=("cn", "en"), default="cn",
                    help="星期表头语言, 默认 cn")
    ap.add_argument("--highlight", default="",
                    help="高亮日期, 逗号分隔, 如 2026-12-25,2026-12-31")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--color", action="store_true", help="强制使用 ANSI 反显高亮")
    grp.add_argument("--plain", action="store_true", help="禁用 ANSI, 用 * 后缀标记")
    args = ap.parse_args()

    today = date.today()
    if args.year is None and args.quarter is None:
        year, quarter = today.year, (today.month - 1) // 3 + 1
    elif args.year is None or args.quarter is None:
        ap.error("年 与 季度 需同时提供, 或都不提供(渲染当前季度)")
    else:
        year, quarter = args.year, args.quarter
    if not 1 <= quarter <= 4:
        ap.error(f"季度应为 1-4, 得到 {quarter}")
    try:
        date(year, 1, 1)
    except ValueError:
        ap.error(f"无效年份: {year}")

    months = [quarter * 3 - 2, quarter * 3 - 1, quarter * 3]
    marked = parse_highlight(args.highlight, ap)
    if today.year == year and today.month in months:
        marked.add(today)
    color = (not args.plain) and (args.color or sys.stdout.isatty())
    start = 0 if args.start == "mon" else 6

    blocks = [render_block(year, m, start, args.lang, marked, color)
              for m in months]
    total_w = 3 * GRID_W + 4
    if args.lang == "cn":
        header = f"{year}年 第{quarter}季度（{months[0]}月-{months[2]}月）"
    else:
        header = (f"{year} Q{quarter} "
                  f"({EN_MONTHS[months[0] - 1]} - {EN_MONTHS[months[2] - 1]})")
    print(pad_center(header, total_w).rstrip())
    for li in range(8):
        print("  ".join(pad_r(b[li], GRID_W) for b in blocks).rstrip())
    if marked:
        print(f"[高亮 {len(marked)} 天: "
              f"{'反显' if color else '*'} 标记 = 今天或指定日期]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
