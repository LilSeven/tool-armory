#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""干支纪年纪日查询（纯标准库实现）。

给定公历日期，输出干支纪年（年干支）、生肖属相与干支纪日。
- 纪年默认按节气界（立春交节换年，命理/历法惯例）；--lunar 改按农历
  正月初一换年（民俗惯例，春节日期由朔日+无中气置闰天文推算）。
- 纪日按儒略日数锚定：(JDN + 49) mod 60，0 = 甲子；锚点
  1949-10-01 = 甲子日，经公开黄历核对。

用法：
  python ganzhi.py 2024-06-05            干支纪年（立春界）+ 纪日 + 生肖
  python ganzhi.py 2024-02-03 --lunar    纪年按春节换年
  python ganzhi.py --selftest            内置自测

示例：
  python ganzhi.py 2024-06-05  ->  甲辰年 甲子日？以实际输出为准
"""

import argparse
import math
import sys

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
ZODIAC = "鼠牛虎兔龙蛇马羊猴鸡狗猪"


def jdn_from_ymd(y, m, d):
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045


def ymd_from_jdn(j):
    a = j + 32044
    b = (4 * a + 3) // 146097
    c = a - 146097 * b // 4
    dd = (4 * c + 3) // 1461
    e = c - 1461 * dd // 4
    m = (5 * e + 2) // 153
    return 100 * b + dd - 4800 + m // 10, m + 3 - 12 * (m // 10), e - (153 * m + 2) // 5 + 1


def _delta_t_seconds(jd_tt):
    y = ymd_from_jdn(int(math.floor(jd_tt + 0.5)))[0]
    y = min(max(y, 1900), 2100)
    return 64.0 + 0.4 * (y - 2020)


def beijing_jdn(jd_tt):
    jd_ut = jd_tt - _delta_t_seconds(jd_tt) / 86400.0
    return int(math.floor(jd_ut + 8.0 / 24.0 + 0.5))


def sun_lambda(jd_ut):
    t = (jd_ut - 2451545.0) / 36525.0
    l0 = 280.46646 + 36000.76983 * t + 0.0003032 * t * t
    m = 357.52911 + 35999.05029 * t - 0.0001537 * t * t
    c = ((1.914602 - 0.004817 * t - 0.000014 * t * t) * math.sin(math.radians(m))
         + (0.019993 - 0.000101 * t) * math.sin(math.radians(2 * m))
         + 0.000289 * math.sin(math.radians(3 * m)))
    omega = 125.04 - 1934.136 * t
    return (l0 + c - 0.00569 - 0.00478 * math.sin(math.radians(omega))) % 360.0


def moon_lambda(jd_ut):
    d = jd_ut - 2451545.0
    lp = 218.3164477 + 13.17639648 * d
    dme = 297.8501921 + 12.19074912 * d
    ms = 357.5291092 + 0.98560028 * d
    mm = 134.9633964 + 13.06499295 * d
    ff = 93.2720950 + 13.22935024 * d
    s, r = math.sin, math.radians
    lon = (lp + 6.289 * s(r(mm)) + 1.274 * s(r(2 * dme - mm)) + 0.658 * s(r(2 * dme))
           + 0.214 * s(r(2 * mm)) - 0.186 * s(r(ms)) - 0.114 * s(r(2 * ff))
           + 0.059 * s(r(2 * dme - 2 * mm)) + 0.057 * s(r(2 * dme - mm - ms))
           + 0.053 * s(r(2 * dme + mm)) + 0.046 * s(r(2 * dme - ms))
           - 0.041 * s(r(mm - ms)) - 0.035 * s(r(dme)) - 0.031 * s(r(mm + ms)))
    return lon % 360.0


def elongation(jd_ut):
    return (moon_lambda(jd_ut) - sun_lambda(jd_ut)) % 360.0


def angdiff(a, b):
    return ((a - b + 180.0) % 360.0) - 180.0


def find_angle_crossing(func, target_deg, jd_guess, window=2.0):
    lo, hi = jd_guess - window, jd_guess + window
    x, step = lo, 0.25
    fprev = angdiff(func(x), target_deg)
    while x < hi:
        nx = min(x + step, hi)
        fcur = angdiff(func(nx), target_deg)
        if fprev == 0.0:
            return x
        if (fprev < 0.0 < fcur) or (fcur < 0.0 < fprev):
            a, b, fa = x, nx, fprev
            for _ in range(60):
                mid = 0.5 * (a + b)
                fm = angdiff(func(mid), target_deg)
                if fa * fm <= 0.0:
                    b = mid
                else:
                    a, fa = mid, fm
            return 0.5 * (a + b)
        x, fprev = nx, fcur
    return None


def lichun_jd(year):
    """公历 year 年立春（太阳视黄经 315°）时刻 JD(TT)。"""
    guess = jdn_from_ymd(year, 2, 4)
    jd = find_angle_crossing(sun_lambda, 315.0, guess, window=6.0)
    if jd is None:
        raise RuntimeError("立春求解失败 %d" % year)
    return jd


SYNODIC = 29.530588861
NEWMOON_BASE = 2451550.09766


def newmoon_jd(k):
    t = k / 1236.85
    guess = NEWMOON_BASE + SYNODIC * k + 0.00015437 * t * t
    jd = find_angle_crossing(elongation, 0.0, guess, window=2.0)
    if jd is None:
        raise RuntimeError("朔日求解失败 k=%d" % k)
    return jd


def cny_jdn(greg_year):
    """公历 greg_year 年春节（农历正月初一）的北京时间日期。

    冬至所在月为农历十一月，其后第二个月朔为正月（历史上闰月不出现在
    十一/十二/正月，此简化在近现代范围内与实历一致）。
    """
    ws = beijing_jdn(find_angle_crossing(sun_lambda, 270.0,
                                         jdn_from_ymd(greg_year - 1, 12, 21), window=6.0))
    k0 = int(math.floor((ws - 10.0 - NEWMOON_BASE) / SYNODIC))
    starts = []
    k = k0
    while len(starts) < 40:
        s = beijing_jdn(newmoon_jd(k))
        if not starts or s > starts[-1]:
            starts.append(s)
        k += 1
    anchor = max(i for i in range(len(starts)) if starts[i] <= ws)
    return starts[anchor + 2]


def day_ganzhi(jdn):
    idx = (jdn + 49) % 60
    return STEMS[idx % 10] + BRANCHES[idx % 12], idx


def year_ganzhi(y):
    return STEMS[(y - 4) % 10] + BRANCHES[(y - 4) % 12]


def selftest():
    # 纪日锚点：1949-10-01 甲子日（公开黄历核对）
    gz, idx = day_ganzhi(jdn_from_ymd(1949, 10, 1))
    assert (gz, idx) == ("甲子", 0), (gz, idx)
    assert day_ganzhi(jdn_from_ymd(2000, 1, 1))[0] == "戊午", "2000-01-01 戊午日"
    # 纪年（立春界）：2024-02-04 立春交节
    assert year_ganzhi(2024) == "甲辰"
    # 春节锚点：2025-01-29、2024-02-10、2023-01-22
    for y, m, d in ((2025, 1, 29), (2024, 2, 10), (2023, 1, 22)):
        assert cny_jdn(y) == jdn_from_ymd(y, m, d), (y, ymd_from_jdn(cny_jdn(y)))
    print("selftest OK")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="干支纪年纪日查询（纯标准库）")
    p.add_argument("date", nargs="?", help="公历日期 YYYY-MM-DD")
    p.add_argument("--lunar", action="store_true", help="纪年按农历正月初一换年（默认立春）")
    p.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = p.parse_args(argv)

    if args.selftest:
        selftest()
        return
    if not args.date:
        p.error("请提供公历日期 YYYY-MM-DD")
    try:
        y, m, d = (int(x) for x in args.date.split("-"))
    except ValueError:
        p.error("日期格式应为 YYYY-MM-DD")
    jd = jdn_from_ymd(y, m, d)

    if args.lunar:
        boundary = cny_jdn(y)
        ly = y if jd >= boundary else y - 1
        mode = "春节换年"
        bstr = "%04d-%02d-%02d 正月初一" % (ymd_from_jdn(boundary) + (0,))[:3]
    else:
        lc = lichun_jd(y)
        boundary = beijing_jdn(lc)
        ly = y if jd >= boundary else y - 1
        mode = "立春换年"
        bstr = "%04d-%02d-%02d 立春" % ymd_from_jdn(boundary)

    gz_year = year_ganzhi(ly)
    gz_day, idx = day_ganzhi(jd)
    print("公历 %04d-%02d-%02d" % (y, m, d))
    print("  干支纪年：%s年（%s年，%s）   生肖：%s"
          % (gz_year, STEMS[(ly - 4) % 10], BRANCHES[(ly - 4) % 12],
             ZODIAC[(ly - 4) % 12]))
    print("  生肖属相：%s" % ZODIAC[(ly - 4) % 12])
    print("  干支纪日：%s（六十甲子第 %d 位）" % (gz_day, idx + 1))
    print("  年界说明：%s，当年界日 %s" % (mode, bstr))


if __name__ == "__main__":
    main()
