#!/usr/bin/env python3
"""日期年月日加减 —— 对日期加减 N 年/N 月/N 天，正确处理月末溢出回退规则。

用法:
    python date-add.py <日期> [-y N] [-m N] [-d N]

示例命令:
    python date-add.py 2026-01-31 --months 1    # 月末回退：2026-01-31 → 2026-02-28
    python date-add.py 2024-02-29 --years 1     # 闰日回退：2024-02-29 → 2025-02-28
    python date-add.py 2026-11-02 --months -3 --days 5    # 负数即减

规则:
    1) 先把"年×12 + 月"合并为整月平移：当"日"超出目标月的天数时，
       回退到该月最后一天（calendar.monthrange 判定，闰年正确）；
    2) 再按"天"做 timedelta 平移。
    因此 1 月 31 日加 1 个月得 2 月 28 日，不会溢出到 3 月。

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


def fmt_shift(years, months, days):
    parts = []
    for name, val in (("年", years), ("个月", months), ("天", days)):
        if val > 0:
            parts.append(f"{val} {name}")
        elif val < 0:
            parts.append(f"减 {abs(val)} {name}")
    return "、".join(parts) if parts else "0（原样）"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="对日期加减 N 年/N 月/N 天（月末溢出自动回退）。")
    ap.add_argument("date", type=parse_date, help="基准日期 YYYY-MM-DD")
    ap.add_argument("-y", "--years", type=int, default=0, help="要加的年数，可为负（默认 0）")
    ap.add_argument("-m", "--months", type=int, default=0, help="要加的月数，可为负（默认 0）")
    ap.add_argument("-d", "--days", type=int, default=0, help="要加的天数，可为负（默认 0）")
    args = ap.parse_args(argv)

    d = args.date
    months_total = args.years * 12 + args.months
    stepped, clamped = shift_months(d, months_total)
    result = stepped + dt.timedelta(days=args.days)

    print(f"原日期：{d.isoformat()}（{WEEK[d.weekday()]}）")
    print(f"平移量：{fmt_shift(args.years, args.months, args.days)}")
    if clamped:
        last = calendar.monthrange(stepped.year, stepped.month)[1]
        print(f"月末回退：{stepped.year}-{stepped.month:02d} 月只有 {last} 天，"
              f"{d.day} 日回退为 {last} 日")
    print(f"结果：{result.isoformat()}（{WEEK[result.weekday()]}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
