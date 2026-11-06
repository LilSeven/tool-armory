#!/usr/bin/env python3
"""日期差三段计算 —— 计算两日期相差几年几月几日的精确分解及总天数。

用法:
    python date-diff.py <日期A> <日期B>

示例命令:
    python date-diff.py 2024-01-31 2024-03-30
    python date-diff.py 2025-01-15 2026-11-02

规则:
    以较早日期为基准，按"整年 → 整月 → 余天"分解：
    * 整月按"锚日平移 + 月末回退"计（1 月 31 日加 1 个月算 2 月 28 日，
      闰年同理），取不超过较晚日期的最大整月数；
    * 余天 = 锚日到较晚日期的实际天数；
    * 因此"较早日期 + N 年 + N 月 + N 天"可精确还原较晚日期（输出带验算行）。
    另给出总天数与总周数。A 晚于 B 时自动交换并提示。

仅用 Python 标准库；退出码：0 正常，2 参数错误。
"""

import argparse
import calendar
import datetime as dt
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def parse_date(text):
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"日期格式应为 YYYY-MM-DD，收到 {text!r}")


def shift_months(d, months):
    """整月平移（月末回退）。返回 (新日期, 是否发生了回退)。"""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    last = calendar.monthrange(year, month)[1]
    day = min(d.day, last)
    return dt.date(year, month, day), day != d.day


def decompose(a, b):
    """b >= a：返回 (年, 月, 天, 锚日, 是否回退)，使 a + 年/月/天 == b。"""
    months = (b.year - a.year) * 12 + (b.month - a.month)
    anchor, clamped = shift_months(a, months)
    if anchor > b:
        months -= 1
        anchor, clamped = shift_months(a, months)
    days = (b - anchor).days
    return months // 12, months % 12, days, anchor, clamped


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="计算两日期相差几年几月几日的精确分解及总天数。")
    ap.add_argument("date_a", type=parse_date, help="日期 A YYYY-MM-DD")
    ap.add_argument("date_b", type=parse_date, help="日期 B YYYY-MM-DD")
    args = ap.parse_args(argv)

    a, b = args.date_a, args.date_b
    swapped = a > b
    if swapped:
        a, b = b, a

    years, months, days, anchor, clamped = decompose(a, b)
    total = (b - a).days

    print(f"日期A：{args.date_a.isoformat()}（{WEEK[args.date_a.weekday()]}）")
    print(f"日期B：{args.date_b.isoformat()}（{WEEK[args.date_b.weekday()]}）")
    if swapped:
        print("（A 晚于 B，已自动交换为“较早 → 较晚”计算）")
    print(f"精确分解：{years} 年 {months} 个月 {days} 天")
    verify = f"{a.isoformat()} + {years} 年 {months} 个月 → {anchor.isoformat()}"
    if clamped:
        verify += f"（月末回退：{a.day} 日 → {anchor.day} 日）"
    verify += f"，再 + {days} 天 = {b.isoformat()} ✓"
    print(f"  验算：{verify}")
    print(f"总天数：{total} 天（{total // 7} 周 余 {total % 7} 天）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
