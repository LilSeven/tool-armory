#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""月相计算器（纯标准库实现）。

计算给定公历日期的月相名称、照亮比例、月龄，以及下一次满月/新月日期。
算法：由月球视黄经与太阳视黄经之差（距角）确定相位，照亮比例
k = (1 - cos 距角) / 2；满月/新月日期由距角 = 180°/0° 数值求解。
位置采用 Meeus 低精度截断级数，时刻误差约 ±10 分钟，日期结果绝大多数
准确。以下一事件为准的"次日"均按北京时间。

用法：
  python moon-phase.py 2024-01-25
  python moon-phase.py --selftest

示例：
  python moon-phase.py 2024-01-25
  ->  满月，照亮约 99%，下一次新月 2024-02-10
"""

import argparse
import math
import sys


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


SYNODIC = 29.530588861
NEWMOON_BASE = 2451550.09766


def phase_event_jd(target_deg, jd_after):
    """求 jd_after 之后（严格大于）第一次距角到达 target_deg 的时刻。"""
    k = math.ceil((jd_after - 4.0 - NEWMOON_BASE) / SYNODIC) if target_deg == 0.0 \
        else math.ceil((jd_after - 4.0 - NEWMOON_BASE - SYNODIC / 2.0) / SYNODIC)
    for _ in range(6):
        t = NEWMOON_BASE + SYNODIC * k + (SYNODIC / 2.0 if target_deg == 180.0 else 0.0)
        jd = find_angle_crossing(elongation, target_deg, t, window=3.0)
        if jd is not None and jd > jd_after - 1e-9:
            return jd
        k += 1
    raise RuntimeError("月相时刻求解失败")


def prev_newmoon_jd(jd0):
    """jd0 之前（含）最近一次朔的时刻。"""
    k = int(math.floor((jd0 - NEWMOON_BASE) / SYNODIC)) + 1
    for _ in range(4):
        t = NEWMOON_BASE + SYNODIC * k
        jd = find_angle_crossing(elongation, 0.0, t, window=2.0)
        if jd is not None and jd <= jd0 + 1e-9:
            return jd
        k -= 1
    raise RuntimeError("朔日求解失败")


def phase_name(elong_deg):
    e = elong_deg % 360.0
    if e < 11.25 or e >= 348.75:
        return "新月"
    if e < 78.75:
        return "娥眉月（盈）"
    if e <= 101.25:
        return "上弦月"
    if e < 168.75:
        return "盈凸月"
    if e <= 191.25:
        return "满月"
    if e < 258.75:
        return "亏凸月"
    if e <= 281.25:
        return "下弦月"
    return "残月（亏）"


def illuminated_fraction(elong_deg):
    return (1.0 - math.cos(math.radians(elong_deg))) / 2.0


def selftest():
    # 已知朔望（公开月相历表）：2024-01-11 新月（11:57 UT，北京 19:57）、
    # 2024-09-18 满月（02:34 UT，北京 10:34）、2024-02-10 新月（甲辰年春节）
    for y, m, d, target in ((2024, 1, 11, "new"), (2024, 9, 18, "full"),
                            (2024, 2, 10, "new")):
        jd = jdn_from_ymd(y, m, d) + 0.5 - 8.0 / 24.0  # 北京时间当日零点(UT)
        ev = phase_event_jd(0.0 if target == "new" else 180.0, jd - 1.0)
        assert beijing_jdn(ev) == jdn_from_ymd(y, m, d), (target, y, m, d)
    jd = jdn_from_ymd(2024, 1, 25) + 0.5 - 8.0 / 24.0
    k = illuminated_fraction(elongation(jd))
    assert k > 0.95, k
    jd = jdn_from_ymd(2024, 1, 11) + 0.5 - 8.0 / 24.0
    assert illuminated_fraction(elongation(jd)) < 0.05
    # 月龄：满月日约 14 天，朔日约 0 天
    age_full = jdn_from_ymd(2024, 1, 25) + 0.5 - 8.0 / 24.0 - prev_newmoon_jd(jdn_from_ymd(2024, 1, 25) + 0.5 - 8.0 / 24.0)
    assert 13.0 < age_full < 15.5, age_full
    age_new = jdn_from_ymd(2024, 1, 11) + 0.5 - 8.0 / 24.0 - prev_newmoon_jd(jdn_from_ymd(2024, 1, 11) + 0.5 - 8.0 / 24.0)
    assert -0.5 <= age_new < 1.5, age_new
    print("selftest OK")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="月相计算器（纯标准库）")
    p.add_argument("date", nargs="?", help="公历日期 YYYY-MM-DD")
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

    jd0 = jdn_from_ymd(y, m, d) + 0.5 - 8.0 / 24.0  # 北京时间当日零点（UT）
    e = elongation(jd0)
    illum = illuminated_fraction(e)
    # 月龄：上一次朔至今
    prev_new = prev_newmoon_jd(jd0)
    age = jd0 - prev_new
    next_new_jd = phase_event_jd(0.0, jd0 + 1.0)
    next_full_jd = phase_event_jd(180.0, jd0 + 1.0)
    ny, nm, nd = ymd_from_jdn(beijing_jdn(next_new_jd))
    fy, fm, fd = ymd_from_jdn(beijing_jdn(next_full_jd))
    waxing = e < 180.0
    print("公历 %04d-%02d-%02d（北京时间零点）" % (y, m, d))
    print("  月相：%s   照亮比例：%.0f%%   月龄：%.1f 天"
          % (phase_name(e), illum * 100.0, age))
    print("  月相增亏：%s" % ("盈（渐圆）" if waxing else "亏（渐缺）"))
    print("  下一次新月：%04d-%02d-%02d" % (ny, nm, nd))
    print("  下一次满月：%04d-%02d-%02d" % (fy, fm, fd))


if __name__ == "__main__":
    main()
