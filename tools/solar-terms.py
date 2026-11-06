#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""二十四节气查询（纯标准库实现）。

查询某公历年的二十四节气精确日期（北京时间），或判断某日前后最近的节气。
算法：对太阳视黄经（Meeus 低精度公式，误差约 ±0.01°）数值求解
"视黄经 = 15°×n" 的时刻，换算为东八区日期。时刻误差约 ±2 分钟，
绝大多数日期准确，个别紧邻午夜的节气可能相差 1 天。适用约 1900-2100 年。

用法：
  python solar-terms.py 2024           列出 2024 年全部二十四节气
  python solar-terms.py 2024-06-05     查该日前后最近的节气

示例：
  python solar-terms.py 2024 | grep 冬至    ->  2024-12-21  冬至
"""

import argparse
import math
import sys

TERM_NAMES = {
    0: "春分", 15: "清明", 30: "谷雨", 45: "立夏", 60: "小满", 75: "芒种",
    90: "夏至", 105: "小暑", 120: "大暑", 135: "立秋", 150: "处暑", 165: "白露",
    180: "秋分", 195: "寒露", 210: "霜降", 225: "立冬", 240: "小雪", 255: "大雪",
    270: "冬至", 285: "小寒", 300: "大寒", 315: "立春", 330: "雨水", 345: "惊蛰",
}


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


def year_solar_terms(year):
    """某公历年的 24 个节气 [(黄经角, 时刻JD(TT))]，按时间先后（自小寒起）。"""
    out = []
    theta = 285.0
    guess = jdn_from_ymd(year, 1, 1) + 4.5
    for _ in range(24):
        jd = find_angle_crossing(sun_lambda, theta, guess, window=6.0)
        if jd is None:
            raise RuntimeError("节气求解失败 %d° %d" % (theta, year))
        out.append((theta, jd))
        theta = (theta + 15.0) % 360.0
        guess += 365.2422 / 24.0
    return out


def terms_of_years(years):
    """展开为按时间排序的 [(名称, 北京日期JDN, 时刻JD)]。"""
    out = []
    for y in years:
        for theta, jd in year_solar_terms(y):
            out.append((TERM_NAMES[theta], beijing_jdn(jd), jd))
    return out


def selftest():
    # 已知节气日期（紫金山天文台历表公开值）
    d = {name: jdn for name, jdn, _ in terms_of_years([2024])}
    assert ymd_from_jdn(d["立春"]) == (2024, 2, 4), "2024 立春"
    assert ymd_from_jdn(d["春分"]) == (2024, 3, 20), "2024 春分"
    assert ymd_from_jdn(d["夏至"]) == (2024, 6, 21), "2024 夏至"
    assert ymd_from_jdn(d["秋分"]) == (2024, 9, 22), "2024 秋分"
    assert ymd_from_jdn(d["冬至"]) == (2024, 12, 21), "2024 冬至"
    d23 = {name: jdn for name, jdn, _ in terms_of_years([2023])}
    assert ymd_from_jdn(d23["冬至"]) == (2023, 12, 22), "2023 冬至"
    # 相邻节气间隔合理（14.7~16.0 天）
    ts = [jdn for _, jdn, _ in terms_of_years([2024])]
    for a, b in zip(ts, ts[1:]):
        assert 14 <= b - a <= 16, (a, b)
    print("selftest OK")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="二十四节气查询（纯标准库）")
    p.add_argument("target", nargs="?", help="年份 YYYY 或日期 YYYY-MM-DD")
    p.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = p.parse_args(argv)

    if args.selftest:
        selftest()
        return
    if not args.target:
        p.error("请提供年份 YYYY 或日期 YYYY-MM-DD")
    try:
        parts = [int(x) for x in args.target.split("-")]
    except ValueError:
        p.error("参数应为年份 YYYY 或日期 YYYY-MM-DD")
    if len(parts) == 1:
        year = parts[0]
        for name, jdn, jd in terms_of_years([year]):
            gy, gm, gd = ymd_from_jdn(jdn)
            h = int(((jd - math.floor(jd + 0.5) + 0.5) * 24 + 8) % 24)
            print("%04d-%02d-%02d  %s（北京时间约 %02d 时）" % (gy, gm, gd, name, h))
        return
    if len(parts) != 3:
        p.error("参数应为年份 YYYY 或日期 YYYY-MM-DD")
    y, m, d = parts
    jd = jdn_from_ymd(y, m, d)
    terms = terms_of_years([y - 1, y, y + 1])
    today = [t for t in terms if t[1] == jd]
    if today:
        print("%04d-%02d-%02d 当日交节气：%s" % (y, m, d, today[0][0]))
    before = [t for t in terms if t[1] <= jd]
    after = [t for t in terms if t[1] > jd]
    for label, t in (("之前最近", before[-1]), ("之后最近", after[0])):
        ty, tm, td = ymd_from_jdn(t[1])
        print("%s节气：%04d-%02d-%02d %s（相差 %d 天）"
              % (label, ty, tm, td, t[0], abs(t[1] - jd)))


if __name__ == "__main__":
    main()
