#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""波斯历换算：公历与伊朗 Jalali（Solar Hijri，太阳希吉来历）互转，输出波斯月名。

用法:
    python persian-calendar.py g2p 2024-03-20    # 公历 -> 波斯历
    python persian-calendar.py p2g 1403-01-01    # 波斯历(年-月-日) -> 公历
    python persian-calendar.py nowruz 2024       # 估算某公历年内的诺鲁孜新年（1 Farvardin）
    python persian-calendar.py --selftest        # 内置自测

说明:
    - 采用 33 年周期算术算法（Pournader & Toossi 的 jalali 算法），
      支持范围约公历 1600-03-01 至 2200 年（波斯历 979 年起）；
    - 波斯历以春分为岁首（诺鲁孜 Nowruz，1 Farvardin），前 6 个月 31 天，
      后 5 个月 30 天，末月平年 29 天 / 闰年 30 天；
    - 该算术历与天文观测（春分时刻）在极少数年份可能相差一天。

示例输出:
    $ python persian-calendar.py g2p 2024-03-20
    公历 2024-03-20 = 波斯历(Solar Hijri) 1403年 Farvardin(法尔瓦尔丁月) 1日 [1403-01-01]
"""

import sys
from datetime import date, timedelta

_G_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
_J_DAYS = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]

MONTH_NAMES = [
    ("法尔瓦尔丁月", "Farvardin"),
    ("奥尔迪贝赫什特月", "Ordibehesht"),
    ("霍尔达德月", "Khordad"),
    ("提尔月", "Tir"),
    ("莫尔达德月", "Mordad"),
    ("沙赫里瓦尔月", "Shahrivar"),
    ("梅赫尔月", "Mehr"),
    ("阿班月", "Aban"),
    ("阿扎尔月", "Azar"),
    ("代月", "Dey"),
    ("巴赫曼月", "Bahman"),
    ("埃斯凡德月", "Esfand"),
]

BASE_YEAR = 1600  # day 0 = 公历 1600-01-01


def _reconfigure():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _greg_leap(y):
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def _greg_month_days(y, m):
    return _G_DAYS[m - 1] + (1 if (m == 2 and _greg_leap(y)) else 0)


def gregorian_to_dayno(y, m, d):
    """公历 (y,m,d) -> 距 1600-01-01 的天数（仅支持 y>=1600）。"""
    if y < BASE_YEAR:
        raise ValueError("仅支持公历 %d 年及以后（当前算法范围约 1600~2200 年）" % BASE_YEAR)
    gy = y - BASE_YEAR
    n = 365 * gy + (gy + 3) // 4 - (gy + 99) // 100 + (gy + 399) // 400
    for i in range(m - 1):
        n += _G_DAYS[i]
    if m > 2 and _greg_leap(y):
        n += 1
    n += d - 1
    if n < 79:
        raise ValueError("仅支持公历约 1600-03-21 之后（波斯历 979 年起）")
    return n


def dayno_to_gregorian(n):
    """距 1600-01-01 的天数 -> 公历 (y,m,d)。"""
    y = BASE_YEAR
    while True:
        dy = 366 if _greg_leap(y) else 365
        if n < dy:
            break
        n -= dy
        y += 1
    m = 1
    for m in range(1, 13):
        dim = _greg_month_days(y, m)
        if n < dim:
            return y, m, n + 1
        n -= dim
    raise AssertionError("unreachable")


def gregorian_to_jalali(y, m, d):
    """公历 -> 波斯历 (jy, jm, jd)。"""
    g_day_no = gregorian_to_dayno(y, m, d)
    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053  # 12053 = 33*365 + 8
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365
    i = 0
    while i < 11 and j_day_no >= _J_DAYS[i]:
        j_day_no -= _J_DAYS[i]
        i += 1
    return jy, i + 1, j_day_no + 1


def jalali_to_dayno(jy, jm, jd):
    """波斯历 (jy,jm,jd) -> 距 1600-01-01 的天数。"""
    if jy < 979:
        raise ValueError("仅支持波斯历 979 年（公历约 1600 年）及以后")
    if not (1 <= jm <= 12):
        raise ValueError("月份须为 1~12: %r" % jm)
    jy2 = jy - 979
    j_day_no = 365 * jy2 + (jy2 // 33) * 8 + ((jy2 % 33) + 3) // 4
    for i in range(jm - 1):
        j_day_no += _J_DAYS[i]
    # 末月天数：闰年 30，平年 29（闰年判据与 33 年周期一致）
    if jm == 12:
        jy3 = jy2 + 1
        next_new_year = 365 * jy3 + (jy3 // 33) * 8 + ((jy3 % 33) + 3) // 4
        dim = next_new_year - j_day_no
        if not (1 <= jd <= dim):
            raise ValueError("日 %r 超出 %d 年 12 月范围（1~%d）" % (jd, jy, dim))
    else:
        if not (1 <= jd <= _J_DAYS[jm - 1]):
            raise ValueError("日 %r 超出 %d 年 %d 月范围（1~%d）" % (jd, jy, jm, _J_DAYS[jm - 1]))
    j_day_no += jd - 1
    return j_day_no + 79


def jalali_to_gregorian(jy, jm, jd):
    """波斯历 -> 公历 (y,m,d)。"""
    n = jalali_to_dayno(jy, jm, jd)
    return dayno_to_gregorian(n)


def jalali_leap(jy):
    """33 年周期下的波斯历闰年（Esfand 30 天）。"""
    jy2 = jy - 979
    this = 365 * jy2 + (jy2 // 33) * 8 + ((jy2 % 33) + 3) // 4
    jy3 = jy2 + 1
    nxt = 365 * jy3 + (jy3 // 33) * 8 + ((jy3 % 33) + 3) // 4
    return nxt - this == 366


def parse_date(text):
    parts = text.strip().split("-")
    if len(parts) != 3:
        raise ValueError("日期格式应为 YYYY-MM-DD: %r" % text)
    return int(parts[0]), int(parts[1]), int(parts[2])


def _describe(jm):
    cn, en = MONTH_NAMES[jm - 1]
    return "%s(%s)" % (en, cn)


def cmd_g2p(text):
    y, m, d = parse_date(text)
    jy, jm, jd = gregorian_to_jalali(y, m, d)
    tag = " 【诺鲁孜新年】" if (jm == 1 and jd == 1) else ""
    print("公历 %04d-%02d-%02d = 波斯历(Solar Hijri) %d年 %s %d日 [%d-%02d-%02d]%s"
          % (y, m, d, jy, _describe(jm), jd, jy, jm, jd, tag))
    return 0


def cmd_p2g(text):
    jy, jm, jd = parse_date(text)
    y, m, d = jalali_to_gregorian(jy, jm, jd)
    tag = " 【诺鲁孜新年】" if (jm == 1 and jd == 1) else ""
    print("波斯历(Solar Hijri) %d年 %s %d日 = 公历 %04d-%02d-%02d%s"
          % (jy, _describe(jm), jd, y, m, d, tag))
    return 0


def cmd_nowruz(text):
    """估算某公历年内诺鲁孜（波斯历新年 1 Farvardin）的公历日期。"""
    gy = int(text.strip())
    jan1 = date(gy, 1, 1).toordinal()
    dec31 = date(gy, 12, 31).toordinal()
    found = 0
    for jy in range(gregorian_to_jalali(gy, 1, 1)[0],
                    gregorian_to_jalali(gy, 12, 31)[0] + 1):
        y, m, d = jalali_to_gregorian(jy, 1, 1)
        if jan1 <= date(y, m, d).toordinal() <= dec31:
            print("诺鲁孜 Nowruz（波斯历 %d 年 1 月 1 日）= 公历 %04d-%02d-%02d" % (jy, y, m, d))
            found += 1
    if not found:
        print("%d 年公历范围内未找到诺鲁孜。" % gy)
    return 0


def selftest():
    # 已知锚点：波斯历新年（诺鲁孜）
    assert gregorian_to_jalali(2024, 3, 20) == (1403, 1, 1)
    assert jalali_to_gregorian(1403, 1, 1) == (2024, 3, 20)
    assert gregorian_to_jalali(2025, 3, 21) == (1404, 1, 1)
    assert jalali_to_gregorian(1404, 1, 1) == (2025, 3, 21)
    # 2026-11-02 = 1405-08-11（Aban 11）
    assert gregorian_to_jalali(2026, 11, 2) == (1405, 8, 11)
    # 平年/闰年天数：1403 闰年 366 天，1404 平年 365 天
    assert jalali_to_dayno(1404, 1, 1) - jalali_to_dayno(1403, 1, 1) == 366
    assert jalali_to_dayno(1405, 1, 1) - jalali_to_dayno(1404, 1, 1) == 365
    # 双向往返：公历 1600-03-21 ~ 2200-12-31 逐日
    day = date(1600, 3, 21)
    end = date(2200, 12, 31)
    step = timedelta(days=1)
    while day < end:
        jy, jm, jd = gregorian_to_jalali(day.year, day.month, day.day)
        assert jalali_to_gregorian(jy, jm, jd) == (day.year, day.month, day.day), (jy, jm, jd, day)
        day += step
    print("persian-calendar selftest OK")


def main(argv):
    _reconfigure()
    if argv and argv[0] == "--selftest":
        selftest()
        return 0
    try:
        if len(argv) == 2 and argv[0] == "g2p":
            return cmd_g2p(argv[1])
        if len(argv) == 2 and argv[0] == "p2g":
            return cmd_p2g(argv[1])
        if len(argv) == 2 and argv[0] == "nowruz":
            return cmd_nowruz(argv[1])
    except (ValueError, OverflowError) as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 2
    print(__doc__.strip())
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
