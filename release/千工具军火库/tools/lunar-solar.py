#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公农历互转（纯标准库实现）。

公历日期与农历日期双向换算，支持闰月，输出农历月、日与天干地支年、生肖。
算法：朔日由"日月视黄经会合（黄经差 = 0）"数值求解，闰月按"无中气置闰"
规则确定，全部采用东八区（UTC+8）日期。日月位置使用截断级数（Meeus 低精
度公式），时刻误差约 ±10 分钟，按日的结果绝大多数准确，个别紧邻午夜的
天文事件可能有 ±1 天偏差。适用范围约 1900-2100 年。

用法：
  python lunar-solar.py 2025-08-23              公历 -> 农历
  python lunar-solar.py --to-solar 2025 6 13    农历平月 -> 公历
  python lunar-solar.py --to-solar 2025 6 1 --leap   农历闰六月 -> 公历
  python lunar-solar.py --selftest              内置一致性自测

示例：
  python lunar-solar.py 2025-01-29
  -> 公历 2025-01-29 = 农历 乙巳年 正月初一（春节），蛇年
"""

import argparse
import math
import sys

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
ZODIAC = "鼠牛虎兔龙蛇马羊猴鸡狗猪"
MONTH_NAMES = ["正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"]


# ---------------- 公历 <-> 儒略日 ----------------

def jdn_from_ymd(y, m, d):
    """格里历日期 -> 儒略日数（整数，当日正午）。"""
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045


def ymd_from_jdn(j):
    """儒略日数 -> 格里历 (年, 月, 日)。"""
    a = j + 32044
    b = (4 * a + 3) // 146097
    c = a - 146097 * b // 4
    dd = (4 * c + 3) // 1461
    e = c - 1461 * dd // 4
    m = (5 * e + 2) // 153
    return 100 * b + dd - 4800 + m // 10, m + 3 - 12 * (m // 10), e - (153 * m + 2) // 5 + 1


def _delta_t_seconds(jd_tt):
    """TT-UT1 粗略近似（秒），对按日结果足够。"""
    y = ymd_from_jdn(int(math.floor(jd_tt + 0.5)))[0]
    y = min(max(y, 1900), 2100)
    return 64.0 + 0.4 * (y - 2020)


def beijing_jdn(jd_tt):
    """力学时 JD -> 该天文时刻对应的北京时间日期的儒略日数。"""
    jd_ut = jd_tt - _delta_t_seconds(jd_tt) / 86400.0
    return int(math.floor(jd_ut + 8.0 / 24.0 + 0.5))


# ---------------- 天体视黄经（Meeus 截断级数，输入 UT） ----------------

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
    """日月视黄经差（地心距角，0-360）。"""
    return (moon_lambda(jd_ut) - sun_lambda(jd_ut)) % 360.0


def angdiff(a, b):
    """a-b 的有符号差，范围 (-180, 180]。"""
    return ((a - b + 180.0) % 360.0) - 180.0


def find_angle_crossing(func, target_deg, jd_guess, window=2.0):
    """在 jd_guess 附近找 func(jd) == target_deg (mod 360) 的时刻。"""
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


# ---------------- 朔日与节气 ----------------

SYNODIC = 29.530588861
NEWMOON_BASE = 2451550.09766


def newmoon_jd(k):
    """第 k 个平均朔的精确时刻（力学时 JD）。"""
    t = k / 1236.85
    guess = NEWMOON_BASE + SYNODIC * k + 0.00015437 * t * t
    jd = find_angle_crossing(elongation, 0.0, guess, window=2.0)
    if jd is None:
        raise RuntimeError("朔日求解失败 k=%d" % k)
    return jd


TERM_NAMES = {
    0: "春分", 15: "清明", 30: "谷雨", 45: "立夏", 60: "小满", 75: "芒种",
    90: "夏至", 105: "小暑", 120: "大暑", 135: "立秋", 150: "处暑", 165: "白露",
    180: "秋分", 195: "寒露", 210: "霜降", 225: "立冬", 240: "小雪", 255: "大雪",
    270: "冬至", 285: "小寒", 300: "大寒", 315: "立春", 330: "雨水", 345: "惊蛰",
}


def year_solar_terms(year):
    """某公历年发生的 24 个节气 [(黄经角, 时刻JD(TT))]，按时间先后（自小寒起）。"""
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


def winter_solstice_jd(year):
    for theta, jd in year_solar_terms(year):
        if theta == 270.0:
            return jd
    raise RuntimeError("冬至求解失败 %d" % year)


def zhongqi_jdns(years):
    """若干公历年内全部十二中气的北京时间日期集合。"""
    s = set()
    for y in years:
        for theta, jd in year_solar_terms(y):
            if theta % 30.0 == 0.0:
                s.add(beijing_jdn(jd))
    return s


def month_starts(jdn_lo, jdn_hi):
    """覆盖 [jdn_lo, jdn_hi] 的朔日序列（北京时间日期 JDN，严格递增）。"""
    k_lo = int(math.floor((jdn_lo - 9.0 - NEWMOON_BASE) / SYNODIC))
    k_hi = int(math.ceil((jdn_hi + 2.0 - NEWMOON_BASE) / SYNODIC))
    out = []
    for k in range(k_lo, k_hi + 1):
        s = beijing_jdn(newmoon_jd(k))
        if not out or s > out[-1]:
            out.append(s)
    return out


def lunar_calendar_chain(year):
    """以 (公历 year-1 年) 冬至所在月为锚点十一月，向后排定月序。

    返回 [(农历年, 月号, 是否闰月, 起始JDN, 结束JDN)]，覆盖锚点前
    40 天到 (公历 year 年) 冬至后 45 天。
    """
    ws_prev = beijing_jdn(winter_solstice_jd(year - 1))
    ws_next = beijing_jdn(winter_solstice_jd(year))
    starts = month_starts(ws_prev - 40, ws_next + 45)
    zq = zhongqi_jdns((year - 2, year - 1, year, year + 1, year + 2))
    anchor = 0
    for i in range(len(starts) - 1):
        if starts[i] <= ws_prev < starts[i + 1]:
            anchor = i
            break
    months = []
    i = anchor
    num, leap, leap_used, ly = 11, False, False, year - 1
    while i + 1 < len(starts):
        s, e = starts[i], starts[i + 1] - 1
        months.append((ly, num, leap, s, e))
        i += 1
        cand = num % 12 + 1
        if cand == 1:
            ly += 1
        if cand == 11:
            leap_used = False
        has_zq = (i + 1 < len(starts)
                  and any(x in zq for x in range(starts[i], starts[i + 1])))
        if cand != 11 and not leap_used and not has_zq:
            leap, leap_used = True, True   # 无中气之月置闰，月号承前
        else:
            num, leap = cand, False
    return months


# ---------------- 双向换算 ----------------

def solar_to_lunar(y, m, d):
    jd = jdn_from_ymd(y, m, d)
    for ly, num, leap, s, e in lunar_calendar_chain(y):
        if s <= jd <= e:
            return {"ly": ly, "month": num, "leap": leap,
                    "day": jd - s + 1, "month_days": e - s + 1}
    raise RuntimeError("公农历换算失败 %04d-%02d-%02d" % (y, m, d))


def lunar_to_solar(ly, month, day, leap=False):
    months = lunar_calendar_chain(ly)
    for cy, num, lp, s, e in months:
        if cy == ly and num == month and lp == leap:
            if not 1 <= day <= e - s + 1:
                raise ValueError(
                    "%d年%s%s只有%d天" % (ly, "闰" if leap else "",
                                          MONTH_NAMES[month - 1], e - s + 1))
            return s + day - 1
    raise ValueError("找不到该农历月：%d年%s%s（当年可能无此闰月）"
                     % (ly, "闰" if leap else "", MONTH_NAMES[month - 1]))


def lunar_day_name(d):
    digits = "一二三四五六七八九十"
    if d == 10:
        return "初十"
    if d == 20:
        return "二十"
    if d == 30:
        return "三十"
    if d < 10:
        return "初" + digits[d - 1]
    if d < 20:
        return "十" + digits[d - 11]
    return "廿" + digits[d - 21]


def ganzhi_year(ly):
    return STEMS[(ly - 4) % 10] + BRANCHES[(ly - 4) % 12]


# ---------------- 自测 ----------------

def selftest():
    # 儒略日换算往返
    for j in range(jdn_from_ymd(1900, 1, 1), jdn_from_ymd(2101, 1, 1), 97):
        y, m, d = ymd_from_jdn(j)
        assert jdn_from_ymd(y, m, d) == j, (j, y, m, d)
    # 已知锚点（公开历表核对）
    assert solar_to_lunar(2025, 1, 29) == {"ly": 2025, "month": 1, "leap": False,
                                           "day": 1, "month_days": 30}, "2025 春节"
    assert solar_to_lunar(2024, 2, 10)["month"] == 1 and solar_to_lunar(2024, 2, 10)["day"] == 1, "2024 春节"
    assert solar_to_lunar(2023, 1, 22)["month"] == 1 and solar_to_lunar(2023, 1, 22)["day"] == 1, "2023 春节"
    assert ymd_from_jdn(lunar_to_solar(2025, 6, 1, leap=True)) == (2025, 7, 25), "2025 闰六月初一"
    # 往返一致（含闰月年前后逐日）
    for j in range(jdn_from_ymd(2019, 1, 1), jdn_from_ymd(2027, 1, 1)):
        y, m, d = ymd_from_jdn(j)
        info = solar_to_lunar(y, m, d)
        j2 = lunar_to_solar(info["ly"], info["month"], info["day"], info["leap"])
        assert j2 == j, (y, m, d, info)
    print("selftest OK")


# ---------------- 命令行 ----------------

def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="公农历互转（含闰月，纯标准库）")
    p.add_argument("date", nargs="?", help="公历日期 YYYY-MM-DD")
    p.add_argument("--to-solar", nargs=3, type=int, metavar=("年", "月", "日"),
                   help="农历转公历：农历年 月 日")
    p.add_argument("--leap", action="store_true", help="配合 --to-solar 指定闰月")
    p.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = p.parse_args(argv)

    if args.selftest:
        selftest()
        return
    if args.to_solar:
        ly, lm, ld = args.to_solar
        j = lunar_to_solar(ly, lm, ld, args.leap)
        gy, gm, gd = ymd_from_jdn(j)
        mname = ("闰" if args.leap else "") + MONTH_NAMES[lm - 1] + "月"
        print("农历 %d年%s%s = 公历 %04d-%02d-%02d"
              % (ly, mname, lunar_day_name(ld), gy, gm, gd))
        return
    if not args.date:
        p.error("请提供公历日期 YYYY-MM-DD，或使用 --to-solar / --selftest")
    try:
        y, m, d = (int(x) for x in args.date.split("-"))
    except ValueError:
        p.error("日期格式应为 YYYY-MM-DD")
    info = solar_to_lunar(y, m, d)
    mname = ("闰" if info["leap"] else "") + MONTH_NAMES[info["month"] - 1] + "月"
    gz = ganzhi_year(info["ly"])
    sx = ZODIAC[(info["ly"] - 4) % 12]
    print("公历 %04d-%02d-%02d = 农历 %s年 %s%s（%s年，该月%d天）"
          % (y, m, d, gz, mname, lunar_day_name(info["day"]), sx, info["month_days"]))


if __name__ == "__main__":
    main()
