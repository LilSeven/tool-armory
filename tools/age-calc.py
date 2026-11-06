#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精确年龄计算：周岁、虚岁、总天数，下次生日倒计时与星期几。

用途：
    按出生日期和基准日期（默认今天）计算：
      - 周岁（X 周岁，附 X岁X个月X天 明细）；
      - 虚岁（按传统"出生即1岁、过春节加1岁"口径，内置 1900-2100 年春节表）；
      - 存活总天数；
      - 下一个生日的日期、星期几与倒计时（2月29日出生者在非闰年按2月28日计）。

用法：
    python age-calc.py <出生日期YYYY-MM-DD> [--at YYYY-MM-DD]

示例命令：
    python age-calc.py 1995-06-15                  # 以今天为基准
    python age-calc.py 2000-02-29 --at 2026-11-02  # 2月29日出生的特殊处理

说明：
    - 仅使用 Python 标准库；
    - 退出码：0 成功，2 参数/日期错误。
"""

import argparse
import calendar
import sys
from datetime import date

WEEK_CN = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

# 1900-2100 年每年春节（农历正月初一）对应的公历月日，"MMDD" 依次排列，
# 由通用农历数据表换算生成，并已用 1949-2027 年已知春节日期核验。
_CNY_MMDD = """\
0131 0219 0208 0129 0216 0204 0125 0213 0202 0122
0210 0130 0218 0206 0126 0214 0203 0123 0211 0201
0220 0208 0128 0216 0205 0124 0213 0202 0123 0210
0130 0217 0206 0126 0214 0204 0124 0211 0131 0219
0208 0127 0215 0205 0125 0213 0202 0122 0210 0129
0217 0206 0127 0214 0203 0124 0212 0131 0218 0208
0128 0215 0205 0125 0213 0202 0121 0209 0130 0217
0206 0127 0215 0203 0123 0211 0131 0218 0207 0128
0216 0205 0125 0213 0202 0220 0209 0129 0217 0206
0127 0215 0204 0123 0210 0131 0219 0207 0128 0216
0205 0124 0212 0201 0122 0209 0129 0218 0207 0126
0214 0203 0123 0210 0131 0219 0208 0128 0216 0205
0125 0212 0201 0122 0210 0129 0217 0206 0126 0213
0203 0123 0211 0131 0219 0208 0128 0215 0204 0124
0212 0201 0122 0210 0130 0217 0206 0126 0214 0202
0123 0211 0201 0219 0208 0128 0215 0204 0124 0212
0202 0121 0209 0129 0217 0205 0126 0214 0203 0123
0211 0131 0219 0207 0127 0215 0205 0124 0212 0202
0122 0209 0129 0217 0206 0126 0214 0203 0124 0210
0130 0218 0207 0127 0215 0205 0125 0212 0201 0121
0209
""".split()

_CNY = [date(1900 + i, int(t[:2]), int(t[2:])) for i, t in enumerate(_CNY_MMDD)]


def week_cn(d):
    return WEEK_CN[d.weekday()]


def add_months(d, n):
    total = d.year * 12 + (d.month - 1) + n
    y, m0 = divmod(total, 12)
    m = m0 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def full_months(ev, ref):
    m = (ref.year - ev.year) * 12 + (ref.month - ev.month)
    if m > 0 and add_months(ev, m) > ref:
        m -= 1
    return max(m, 0)


def full_years(ev, ref):
    y = ref.year - ev.year
    try:
        ann = ev.replace(year=ref.year)
    except ValueError:
        ann = date(ref.year, 2, 28)
    if ann > ref:
        y -= 1
    return max(y, 0)


def next_birthday(birth, ref):
    """下一个生日，返回 (date, 是否使用了2月28日替补)。"""
    for y in (ref.year, ref.year + 1):
        try:
            cand = birth.replace(year=y)
            fallback = False
        except ValueError:
            cand = date(y, 2, 28)
            fallback = True
        if cand >= ref:
            return cand, fallback
    raise AssertionError("unreachable")


def lunar_year_of(d):
    """日期 d 所属农历年份；超出春节表范围返回 None。"""
    idx = d.year - 1900
    if not (0 <= idx < len(_CNY)):
        return None
    if d >= _CNY[idx]:
        return d.year
    if d.year - 1 < 1900:
        return None
    return d.year - 1


def virtual_age(birth, ref):
    """虚岁，返回 (虚岁, 是否为精确春节口径)。"""
    by = lunar_year_of(birth)
    ry = lunar_year_of(ref)
    if by is None or ry is None:
        return ref.year - birth.year + 1, False
    return ry - by + 1, True


def run(birth, ref, at_default):
    if ref < birth:
        raise ValueError("基准日期早于出生日期")
    years = full_years(birth, ref)
    months = full_months(birth, ref)
    rest_months = months - years * 12
    anchor = add_months(birth, months)
    rest_days = (ref - anchor).days
    total = (ref - birth).days
    vx, exact = virtual_age(birth, ref)
    nb, fb = next_birthday(birth, ref)

    print(f"出生日期：{birth.isoformat()}（{week_cn(birth)}）")
    print(f"基准日期：{ref.isoformat()}（{week_cn(ref)}）" + ("（默认今天）" if at_default else ""))
    print(f"周岁：{years} 周岁（{years}岁{rest_months}个月{rest_days}天）")
    how = "按春节口径：出生即1岁、过春节加1岁" if exact else "超出春节表范围，按公历年差简化"
    print(f"虚岁：{vx} 虚岁（{how}）")
    print(f"总天数：{total} 天（约 {total / 365.2425:.1f} 年）")
    if nb == ref:
        print(f"下次生日：{nb.isoformat()}（{week_cn(nb)}）——就是今天，生日快乐！")
        return
    tip = "（2月29日出生，非闰年按2月28日）" if fb else ""
    print(f"下次生日：{nb.isoformat()}（{week_cn(nb)}），还有 {(nb - ref).days} 天{tip}")


def parse_date(s):
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        raise argparse.ArgumentTypeError(f"日期格式应为 YYYY-MM-DD，收到：{s!r}")


def _utf8_stdio():
    """在非 UTF-8 控制台/管道下尽量以 UTF-8 输出。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (stream.encoding or "").lower().replace("-", "")
            if enc and enc != "utf8" and hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv=None):
    _utf8_stdio()
    p = argparse.ArgumentParser(
        prog="age-calc.py",
        description="精确年龄计算：周岁、虚岁、总天数，下次生日倒计时与星期几。")
    p.add_argument("birth", type=parse_date, metavar="YYYY-MM-DD", help="出生日期")
    p.add_argument("--at", type=parse_date, metavar="YYYY-MM-DD", default=None,
                   help="基准日期，默认今天")
    args = p.parse_args(argv)
    ref = args.at or date.today()
    try:
        run(args.birth, ref, args.at is None)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
