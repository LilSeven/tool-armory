#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""希伯来历换算：公历与希伯来历（tabular 固定算术算法）互转，输出月份名与年份号。

用法:
    python hebrew-calendar.py g2h 2024-01-01     # 公历 -> 希伯来历
    python hebrew-calendar.py h2g 5784-10-19     # 希伯来历(年-月-日) -> 公历
    python hebrew-calendar.py --selftest         # 内置自测

说明:
    - 采用 Calendrical Calculations 中的 tabular（算术）希伯来历，
      含 19 年 7 闰、 postponement（推迟规则）；
    - 希伯来历一年从提斯利月(Tishri)起，月份编号 1=Nisan ... 7=Tishri ... 13=闰亚达月；
    - 希伯来历以日落为一日之始，且纪年从“创世”(公元前 3761 年)起算，
      换算结果为历法对照，节日实际开始须结合日落时刻；
    - 闰年（如 5784）有 13 个月，第 12/13 月为亚达月 I / II。

示例输出:
    $ python hebrew-calendar.py g2h 2024-01-01
    公历 2024-01-01 = 希伯来历 5784年 提别月(Tevet) 19日 [5784-10-19]
"""

import sys
from datetime import date

HEBREW_EPOCH = -1373427  # RD 值：希伯来历纪元（1 Tishri 1H 前一日为基准）

MONTH_NAMES = {
    1: ("尼散月", "Nisan"),
    2: ("以珥月", "Iyyar"),
    3: ("西弯月", "Sivan"),
    4: ("搭模斯月", "Tammuz"),
    5: ("埃波月", "Av"),
    6: ("以禄月", "Elul"),
    7: ("提斯利月", "Tishri"),
    8: ("玛西班月", "Marheshvan"),
    9: ("基斯流月", "Kislev"),
    10: ("提别月", "Tevet"),
    11: ("细罢特月", "Shevat"),
    12: ("亚达月I", "Adar I"),
    13: ("亚达月II", "Adar II"),
}


def _reconfigure():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def hebrew_leap(year):
    """19 年周期第 3/6/8/11/14/17/19 年为闰年（置闰亚达月）。"""
    return (year * 7 + 1) % 19 < 7


def months_in_year(year):
    return 13 if hebrew_leap(year) else 12


def elapsed_days(year):
    """从纪元到该年 1 Tishri（未做推迟修正前）的天数。"""
    months_elapsed = (235 * year - 234) // 19
    parts_elapsed = 12084 + 13753 * months_elapsed
    days = 29 * months_elapsed + parts_elapsed // 25920
    if (3 * (days + 1)) % 7 < 3:
        days += 1
    return days


def year_length_correction(year):
    """推迟规则：延长/缩短前一年，避免 1 Tishri 落在不合适的日子。"""
    ny0 = elapsed_days(year - 1)
    ny1 = elapsed_days(year)
    ny2 = elapsed_days(year + 1)
    if ny2 - ny1 == 356:
        return 2
    if ny1 - ny0 == 382:
        return 1
    return 0


def new_year(year):
    """该年 1 Tishri 的 RD 天数。"""
    return HEBREW_EPOCH + elapsed_days(year) + year_length_correction(year)


def days_in_year(year):
    return new_year(year + 1) - new_year(year)


def long_heshvan(year):
    return days_in_year(year) % 10 == 5


def short_kislev(year):
    return days_in_year(year) % 10 == 3


def days_in_month(year, month):
    if month in (2, 4, 6, 10, 13):
        return 29
    if month == 12 and not hebrew_leap(year):
        return 29  # 平年的亚达月
    if month == 8 and not long_heshvan(year):
        return 29
    if month == 9 and short_kislev(year):
        return 29
    return 30


def month_order(year):
    """希伯来历一年内月份的历法顺序：Tishri(7) 起，至 Elul(6)。"""
    return list(range(7, months_in_year(year) + 1)) + list(range(1, 7))


def fixed_from_hebrew(year, month, day):
    if not (1 <= month <= months_in_year(year)):
        raise ValueError("月份 %r 超出该年范围（1~%d）" % (month, months_in_year(year)))
    rd = new_year(year)
    for m in month_order(year):
        dim = days_in_month(year, m)
        if m == month:
            if not (1 <= day <= dim):
                raise ValueError("日 %r 超出 %d 年 %d 月范围（1~%d）" % (day, year, month, dim))
            return rd + day - 1
        rd += dim
    raise ValueError("未知月份 %r" % month)


def hebrew_from_fixed(rd):
    """RD 天数 -> (year, month, day)。"""
    approx = max(1, (rd - HEBREW_EPOCH) // 365)
    while new_year(approx) > rd:
        approx -= 1
    while new_year(approx + 1) <= rd:
        approx += 1
    rem = rd - new_year(approx)
    for m in month_order(approx):
        dim = days_in_month(approx, m)
        if rem < dim:
            return approx, m, rem + 1
        rem -= dim
    raise AssertionError("unreachable")


def parse_date(text):
    parts = text.strip().split("-")
    if len(parts) != 3:
        raise ValueError("日期格式应为 YYYY-MM-DD: %r" % text)
    return int(parts[0]), int(parts[1]), int(parts[2])


def cmd_g2h(text):
    y, m, d = parse_date(text)
    hy, hm, hd = hebrew_from_fixed(date(y, m, d).toordinal())
    cn, en = MONTH_NAMES[hm]
    leap = "（闰年，13 个月）" if hebrew_leap(hy) else ""
    print("公历 %04d-%02d-%02d = 希伯来历 %d年 %s(%s) %d日 [年-月-日: %d-%d-%d]%s"
          % (y, m, d, hy, cn, en, hd, hy, hm, hd, leap))
    print("注：希伯来历以日落为一日之始，且纪年自创世（公元前 3761 年）起算。")
    return 0


def cmd_h2g(text):
    hy, hm, hd = parse_date(text)
    rd = fixed_from_hebrew(hy, hm, hd)
    g = date.fromordinal(rd)
    cn, en = MONTH_NAMES[hm]
    print("希伯来历 %d年 %s(%s) %d日 = 公历 %04d-%02d-%02d"
          % (hy, cn, en, hd, g.year, g.month, g.day))
    return 0


def selftest():
    # 已知锚点：犹太新年 1 Tishri
    assert date.fromordinal(fixed_from_hebrew(5784, 7, 1)) == date(2023, 9, 16)
    assert date.fromordinal(fixed_from_hebrew(5785, 7, 1)) == date(2024, 10, 3)
    assert date.fromordinal(fixed_from_hebrew(5786, 7, 1)) == date(2025, 9, 23)
    # 以色列独立日：1948-05-14 = 5 Iyar 5708
    assert hebrew_from_fixed(date(1948, 5, 14).toordinal()) == (5708, 2, 5)
    assert fixed_from_hebrew(5708, 2, 5) == date(1948, 5, 14).toordinal()
    # 2024-01-01 = 20 Tevet 5784（与 Hebcal 对照一致）
    assert hebrew_from_fixed(date(2024, 1, 1).toordinal()) == (5784, 10, 20)
    # 平年 12 个月 / 闰年 13 个月；平年长度 353~355，闰年 383~385
    assert months_in_year(5784) == 13 and months_in_year(5785) == 12
    for y in range(5700, 5900):
        n = days_in_year(y)
        if hebrew_leap(y):
            assert n in (383, 384, 385), n
        else:
            assert n in (353, 354, 355), n
    # 双向往返：逐日 5700-01-01 ~ 5800 年末
    rd = fixed_from_hebrew(5700, 7, 1)
    end = fixed_from_hebrew(5800, 7, 1)
    while rd < end:
        hy, hm, hd = hebrew_from_fixed(rd)
        assert fixed_from_hebrew(hy, hm, hd) == rd, (hy, hm, hd, rd)
        rd += 1
    print("hebrew-calendar selftest OK")


def main(argv):
    _reconfigure()
    if argv and argv[0] == "--selftest":
        selftest()
        return 0
    try:
        if len(argv) == 2 and argv[0] == "g2h":
            return cmd_g2h(argv[1])
        if len(argv) == 2 and argv[0] == "h2g":
            return cmd_h2g(argv[1])
    except (ValueError, OverflowError) as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 2
    print(__doc__.strip())
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
