#!/usr/bin/env python3
"""全年年历渲染 —— 横排(按行并排数月)或竖排(逐月堆叠)渲染整年年历, 支持高亮指定日期。

用法:
  python calendar-year.py                        # 当前年, 横排每行 3 个月
  python calendar-year.py 2026                   # 指定年份
  python calendar-year.py 2026 --cols 4          # 横排每行 4 个月(1-6)
  python calendar-year.py 2026 --layout v        # 竖排: 逐月堆叠(忽略 --cols)
  python calendar-year.py 2026 --highlight 2026-01-01,2026-10-01
  python calendar-year.py 2026 --start sun --lang en --plain

高亮规则: --highlight 指定的日期高亮, 今天在本年内也高亮。
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
    ap = argparse.ArgumentParser(description="横排/竖排渲染整年年历, 支持高亮指定日期")
    ap.add_argument("year", nargs="?", type=int, help="年份(如 2026), 默认当前年")
    ap.add_argument("--layout", choices=("h", "v"), default="h",
                    help="h=横排网格(默认), v=竖排逐月堆叠")
    ap.add_argument("--cols", type=int, choices=range(1, 7), default=3,
                    help="横排时每行月数 1-6, 默认 3")
    ap.add_argument("--start", choices=("mon", "sun"), default="mon",
                    help="一周起始日, 默认 mon")
    ap.add_argument("--lang", choices=("cn", "en"), default="cn",
                    help="星期表头语言, 默认 cn")
    ap.add_argument("--highlight", default="",
                    help="高亮日期, 逗号分隔, 如 2026-01-01,2026-10-01")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--color", action="store_true", help="强制使用 ANSI 反显高亮")
    grp.add_argument("--plain", action="store_true", help="禁用 ANSI, 用 * 后缀标记")
    args = ap.parse_args()

    year = args.year if args.year is not None else date.today().year
    try:
        date(year, 1, 1)
    except ValueError:
        ap.error(f"无效年份: {year}")

    marked = parse_highlight(args.highlight, ap)
    today = date.today()
    if today.year == year:
        marked.add(today)
    color = (not args.plain) and (args.color or sys.stdout.isatty())
    start = 0 if args.start == "mon" else 6
    cols = 1 if args.layout == "v" else args.cols

    blocks = [render_block(year, m, start, args.lang, marked, color)
              for m in range(1, 13)]
    total_w = cols * GRID_W + (cols - 1) * 2
    print(pad_center(f"{year}年" if args.lang == "cn" else str(year), total_w).rstrip())
    for i in range(0, 12, cols):
        chunk = blocks[i:i + cols]
        for li in range(8):
            print("  ".join(pad_r(b[li] if li < len(b) else "", GRID_W)
                            for b in chunk).rstrip())
        if i + cols < 12:
            print()
    if marked:
        print(f"[高亮 {len(marked)} 天: "
              f"{'反显' if color else '*'} 标记 = 今天或指定日期]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
