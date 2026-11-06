#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""周年纪念计算：计算事件发生以来的整周年/整月数，支持公历与农历纪念。

用途：
    以基准日期（默认今天）计算事件发生以来已满的整周年数、整月数与累计
    天数，并给出下一个周年纪念日的公历日期、星期与倒计时。
    事件日期默认按公历解析；加 --lunar 后按农历解析，纪念日按农历日期
    逐年对应的公历日期推算（例如"农历八月十五"对应每年的中秋节）。

用法：
    python anniversary.py <事件日期YYYY-MM-DD> [--at YYYY-MM-DD] [--lunar] [--leap] [--selftest]

示例命令：
    python anniversary.py 2020-01-25                          # 公历事件，以今天为基准
    python anniversary.py 2015-10-01 --at 2026-11-02          # 指定基准日期
    python anniversary.py 1990-08-15 --lunar --at 2026-11-02  # 农历事件（八月十五）
    python anniversary.py 2020-04-15 --lunar --leap           # 农历闰四月十五
    python anniversary.py --selftest                          # 运行农历换算自检

说明：
    - 农历换算基于 1900-2100 年月大小/闰月数据表，超出范围直接报错；
    - 闰月事件用 --leap 标记；某纪念年若无该闰月，退回同序非闰月日期；
    - 公历 2 月 29 日事件在非闰年按 2 月 28 日计纪念日；
    - 仅使用 Python 标准库；退出码：0 成功，2 参数/日期错误，1 自检失败。
"""

import argparse
import calendar
import sys
from datetime import date, timedelta

WEEK_CN = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"
LUNAR_MONTH_NAME = {1: "正", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六",
                    7: "七", 8: "八", 9: "九", 10: "十", 11: "冬", 12: "腊"}

# 农历 1900-2100 年数据表（通用公开数据，与 calendar.js 等实现一致）：
# 低 4 位 = 闰月月份（0 表示该年无闰月）；
# 第 16-m 位（m=1..12）= 第 m 个序号月的大小（1 为 30 天，0 为 29 天）；
# 第 16 位（0x10000）= 闰月的大小（1 为 30 天，0 为 29 天）。
LUNAR_INFO = (
    # 1900-1909
    0x04bd8, 0x04ae0, 0x0a570, 0x054d5, 0x0d260, 0x0d950, 0x16554, 0x056a0, 0x09ad0, 0x055d2,
    # 1910-1919
    0x04ae0, 0x0a5b6, 0x0a4d0, 0x0d250, 0x1d255, 0x0b540, 0x0d6a0, 0x0ada2, 0x095b0, 0x14977,
    # 1920-1929
    0x04970, 0x0a4b0, 0x0b4b5, 0x06a50, 0x06d40, 0x1ab54, 0x02b60, 0x09570, 0x052f2, 0x04970,
    # 1930-1939
    0x06566, 0x0d4a0, 0x0ea50, 0x16a95, 0x05ad0, 0x02b60, 0x186e3, 0x092e0, 0x1c8d7, 0x0c950,
    # 1940-1949
    0x0d4a0, 0x1d8a6, 0x0b550, 0x056a0, 0x1a5b4, 0x025d0, 0x092d0, 0x0d2b2, 0x0a950, 0x0b557,
    # 1950-1959
    0x06ca0, 0x0b550, 0x15355, 0x04da0, 0x0a5b0, 0x14573, 0x052b0, 0x0a9a8, 0x0e950, 0x06aa0,
    # 1960-1969
    0x0aea6, 0x0ab50, 0x04b60, 0x0aae4, 0x0a570, 0x05260, 0x0f263, 0x0d950, 0x05b57, 0x056a0,
    # 1970-1979
    0x096d0, 0x04dd5, 0x04ad0, 0x0a4d0, 0x0d4d4, 0x0d250, 0x0d558, 0x0b540, 0x0b6a0, 0x195a6,
    # 1980-1989
    0x095b0, 0x049b0, 0x0a974, 0x0a4b0, 0x0b27a, 0x06a50, 0x06d40, 0x0af46, 0x0ab60, 0x09570,
    # 1990-1999
    0x04af5, 0x04970, 0x064b0, 0x074a3, 0x0ea50, 0x06b58, 0x05ac0, 0x0ab60, 0x096d5, 0x092e0,
    # 2000-2009
    0x0c960, 0x0d954, 0x0d4a0, 0x0da50, 0x07552, 0x056a0, 0x0abb7, 0x025d0, 0x092d0, 0x0cab5,
    # 2010-2019
    0x0a950, 0x0b4a0, 0x0baa4, 0x0ad50, 0x055d9, 0x04ba0, 0x0a5b0, 0x15176, 0x052b0, 0x0a930,
    # 2020-2029
    0x07954, 0x06aa0, 0x0ad50, 0x05b52, 0x04b60, 0x0a6e6, 0x0a4e0, 0x0d260, 0x0ea65, 0x0d530,
    # 2030-2039
    0x05aa0, 0x076a3, 0x096d0, 0x04afb, 0x04ad0, 0x0a4d0, 0x1d0b6, 0x0d250, 0x0d520, 0x0dd45,
    # 2040-2049
    0x0b5a0, 0x056d0, 0x055b2, 0x049b0, 0x0a577, 0x0a4b0, 0x0aa50, 0x1b255, 0x06d20, 0x0ada0,
    # 2050-2059
    0x14b63, 0x09370, 0x049f8, 0x04970, 0x064b0, 0x168a6, 0x0ea50, 0x06aa0, 0x1a6c4, 0x0aae0,
    # 2060-2069
    0x092e0, 0x0d2e3, 0x0c960, 0x0d557, 0x0d4a0, 0x0da50, 0x05d55, 0x056a0, 0x0a6d0, 0x055d4,
    # 2070-2079
    0x052d0, 0x0a9b8, 0x0a950, 0x0b4a0, 0x0b6a6, 0x0ad50, 0x055a0, 0x0aba4, 0x0a5b0, 0x052b0,
    # 2080-2089
    0x0b273, 0x06930, 0x07337, 0x06aa0, 0x0ad50, 0x14b55, 0x04b60, 0x0a570, 0x054e4, 0x0d160,
    # 2090-2099
    0x0e968, 0x0d520, 0x0daa0, 0x16aa6, 0x056d0, 0x04ae0, 0x0a9d4, 0x0a2d0, 0x0d150, 0x0f252,
    # 2100
    0x0d520,
)

LUNAR_EPOCH = date(1900, 1, 31)  # 农历 1900 年正月初一
LYEAR_MIN, LYEAR_MAX = 1900, 2100


def _leap_month(ly):
    """农历 ly 年的闰月序号，无闰月返回 0。"""
    return LUNAR_INFO[ly - LYEAR_MIN] & 0xF


def _month_days(ly, m):
    """农历 ly 年第 m 个序号月（非闰月）的天数。"""
    return 30 if (LUNAR_INFO[ly - LYEAR_MIN] >> (16 - m)) & 1 else 29


def _leap_days(ly):
    """农历 ly 年闰月的天数，无闰月返回 0。"""
    if not _leap_month(ly):
        return 0
    return 30 if LUNAR_INFO[ly - LYEAR_MIN] & 0x10000 else 29


def _year_days(ly):
    total = 348 + bin(LUNAR_INFO[ly - LYEAR_MIN] & 0xFFF0).count("1")
    return total + _leap_days(ly)


def solar_to_lunar(gd):
    """公历 date -> (农历年, 月, 日, 是否闰月)。"""
    offset = (gd - LUNAR_EPOCH).days
    if offset < 0:
        raise ValueError("农历换算仅支持 1900-01-31 及之后的公历日期")
    ly = LYEAR_MIN
    while ly <= LYEAR_MAX and offset >= _year_days(ly):
        offset -= _year_days(ly)
        ly += 1
    if ly > LYEAR_MAX:
        raise ValueError("农历换算仅支持 2100 年内的农历日期")
    lm_leap = _leap_month(ly)
    m, is_leap = 1, False
    while True:
        md = _month_days(ly, m)
        if offset < md:
            break
        offset -= md
        if m == lm_leap:
            md2 = _leap_days(ly)
            if offset < md2:
                is_leap = True
                break
            offset -= md2
        m += 1
    return ly, m, offset + 1, is_leap


def lunar_to_solar(ly, lm, ld, leap=False):
    """农历 (年, 月, 日, 是否闰月) -> 公历 date。"""
    if not (LYEAR_MIN <= ly <= LYEAR_MAX):
        raise ValueError(f"农历年份需在 {LYEAR_MIN}-{LYEAR_MAX} 之间：{ly}")
    if not (1 <= lm <= 12):
        raise ValueError(f"农历月份需在 1-12 之间：{lm}")
    if leap and lm != _leap_month(ly):
        raise ValueError(f"农历{ly}年没有闰{lunar_month_name(lm, False)}")
    md = _leap_days(ly) if leap else _month_days(ly, lm)
    if not (1 <= ld <= md):
        raise ValueError(f"农历{ly}年{lunar_month_name(lm, leap)}只有 {md} 天，收到 {ld}")
    gd = LUNAR_EPOCH
    for y in range(LYEAR_MIN, ly):
        gd += timedelta(days=_year_days(y))
    for m in range(1, lm):
        gd += timedelta(days=_month_days(ly, m))
        if m == _leap_month(ly):
            gd += timedelta(days=_leap_days(ly))
    if leap:
        gd += timedelta(days=_month_days(ly, lm))
    return gd + timedelta(days=ld - 1)


def lunar_month_name(m, leap):
    return ("闰" if leap else "") + LUNAR_MONTH_NAME[m] + "月"


def lunar_day_name(d):
    if d == 10:
        return "初十"
    if d == 20:
        return "二十"
    if d == 30:
        return "三十"
    return ("初" if d < 10 else "十" if d < 20 else "廿") + "一二三四五六七八九"[d % 10 - 1]


def ganzhi(ly):
    return GAN[(ly - 4) % 10] + ZHI[(ly - 4) % 12]


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


def next_solar_anniversary(ev, ref):
    """下一个（>= ref）公历周年纪念日，返回 (date, 是否使用了2月28日替补)。"""
    for y in (ref.year, ref.year + 1):
        try:
            cand = ev.replace(year=y)
            fallback = False
        except ValueError:
            cand = date(y, 2, 28)
            fallback = True
        if cand >= ref:
            return cand, fallback
    raise AssertionError("unreachable")


def run_solar(ev, ref, at_default):
    if ref < ev:
        raise ValueError("基准日期早于事件日期")
    ann, fb = next_solar_anniversary(ev, ref)
    print(f"事件日期：{ev.isoformat()}（{week_cn(ev)}）")
    print(f"基准日期：{ref.isoformat()}（{week_cn(ref)}）" + ("（默认今天）" if at_default else ""))
    print(f"已满整周年：{full_years(ev, ref)} 周年")
    print(f"已满整月数：{full_months(ev, ref)} 个月")
    print(f"累计总天数：{(ref - ev).days} 天")
    remain = (ann - ref).days
    if remain == 0:
        print(f"下一个周年纪念日：{ann.isoformat()}（{week_cn(ann)}）——就是今天，周年快乐！")
    else:
        tip = "（2月29日事件，非闰年按2月28日）" if fb else ""
        print(f"下一个周年纪念日：{ann.isoformat()}（{week_cn(ann)}），还有 {remain} 天{tip}")


def run_lunar(ly, lm, ld, leap_in, ref, at_default):
    if leap_in and _leap_month(ly) != lm:
        cur = _leap_month(ly)
        desc = "无闰月" if cur == 0 else "闰" + lunar_month_name(cur, False)
        raise ValueError(f"农历{ly}年{desc}，与 --leap 指定的闰{lunar_month_name(lm, False)}不符")
    ev = lunar_to_solar(ly, lm, ld, leap_in)
    if ref < ev:
        raise ValueError("基准日期早于事件日期")
    ry, rm, rd, rleap = solar_to_lunar(ref)
    print(f"事件（农历）：{ly}年（{ganzhi(ly)}年）{lunar_month_name(lm, leap_in)}{lunar_day_name(ld)}"
          f" → 公历 {ev.isoformat()}（{week_cn(ev)}）")
    print(f"基准日期：{ref.isoformat()}（{week_cn(ref)}，农历 {ry}年（{ganzhi(ry)}年）"
          f"{lunar_month_name(rm, rleap)}{lunar_day_name(rd)}）" + ("（默认今天）" if at_default else ""))

    passed, fb_leap, fb_day = 0, 0, 0
    nxt = None
    k = 1
    while ly + k <= LYEAR_MAX:
        ty = ly + k
        use_leap = leap_in and _leap_month(ty) == lm
        try:
            d = lunar_to_solar(ty, lm, ld, use_leap)
            aday = ld
        except ValueError:
            aday = _leap_days(ty) if use_leap else _month_days(ty, lm)
            d = lunar_to_solar(ty, lm, aday, use_leap)
            fb_day += 1
        if d > ref:
            nxt = (ty, d, use_leap, aday)
            break
        if leap_in and not use_leap:
            fb_leap += 1
        passed += 1
        k += 1

    print(f"已满整周年：{passed} 周年（农历口径）")
    if fb_leap:
        print(f"  注：其中 {fb_leap} 个纪念年无闰{lunar_month_name(lm, False)}，已按非闰月计算")
    if fb_day:
        print(f"  注：其中 {fb_day} 个纪念年该月为小月，已按当月最后一天计算")
    print(f"公历口径参考：已满 {full_months(ev, ref)} 个月，累计 {(ref - ev).days} 天")
    if nxt is None:
        print(f"下一个周年纪念日：超出农历数据范围（{LYEAR_MAX} 年），无法推算")
        return
    ty, d, use_leap, aday = nxt
    remain = (d - ref).days
    lstr = (f"农历{ty}年{lunar_month_name(lm, use_leap)}{lunar_day_name(aday)}"
            f" → 公历 {d.isoformat()}（{week_cn(d)}）")
    if remain == 0:
        print(f"下一个周年纪念日：{lstr} —— 就是今天！")
    else:
        print(f"下一个周年纪念日：{lstr}，还有 {remain} 天")


def parse_date(s):
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        raise argparse.ArgumentTypeError(f"日期格式应为 YYYY-MM-DD，收到：{s!r}")


def selftest():
    checks = []

    def chk(name, cond):
        checks.append((name, bool(cond)))

    chk("1900年正月初一 = 1900-01-31", lunar_to_solar(1900, 1, 1) == date(1900, 1, 31))
    cny = {1949: (1, 29), 1950: (2, 17), 1960: (1, 28), 1970: (2, 6), 1980: (2, 16),
           1990: (1, 27), 2000: (2, 5), 2010: (2, 14), 2015: (2, 19), 2018: (2, 16),
           2019: (2, 5), 2020: (1, 25), 2021: (2, 12), 2022: (2, 1), 2023: (1, 22),
           2024: (2, 10), 2025: (1, 29), 2026: (2, 17), 2027: (2, 6)}
    for y in sorted(cny):
        m, d = cny[y]
        chk(f"{y}年春节 = {y}-{m:02d}-{d:02d}", lunar_to_solar(y, 1, 1) == date(y, m, d))
    chk("2020年闰四月", _leap_month(2020) == 4)
    chk("2023年闰二月", _leap_month(2023) == 2)
    chk("2025年闰六月", _leap_month(2025) == 6)
    chk("2025年端午 = 2025-05-31", lunar_to_solar(2025, 5, 5) == date(2025, 5, 31))
    chk("2025年中秋 = 2025-10-06", lunar_to_solar(2025, 8, 15) == date(2025, 10, 6))
    chk("2020年中秋 = 2020-10-01", lunar_to_solar(2020, 8, 15) == date(2020, 10, 1))
    chk("2020年闰四月初一 = 2020-05-23", lunar_to_solar(2020, 4, 1, leap=True) == date(2020, 5, 23))
    chk("2023年闰二月初一 = 2023-03-22", lunar_to_solar(2023, 2, 1, leap=True) == date(2023, 3, 22))
    chk("2025年闰六月初一 = 2025-07-25", lunar_to_solar(2025, 6, 1, leap=True) == date(2025, 7, 25))
    chk("各农历年天数在353-385天之间",
        all(_year_days(y) in (353, 354, 355, 383, 384, 385) for y in range(LYEAR_MIN, LYEAR_MAX + 1)))
    ok = True
    for y in (1901, 1950, 1984, 2000, 2020, 2025, 2040, 2077, 2099):
        d = date(y, 1, 1)
        while d.year == y:
            ly, lm, ld, lp = solar_to_lunar(d)
            if lunar_to_solar(ly, lm, ld, lp) != d:
                ok = False
                break
            d += timedelta(days=7)
    chk("公历→农历→公历往返一致（抽样9年，每隔7天）", ok)

    fails = [name for name, c in checks if not c]
    for name, c in checks:
        print(("PASS  " if c else "FAIL  ") + name)
    print(f"自检完成：共 {len(checks)} 项，通过 {len(checks) - len(fails)} 项，失败 {len(fails)} 项")
    return 0 if not fails else 1


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
        prog="anniversary.py",
        description="周年纪念计算：整周年/整月数，支持公历与农历纪念。")
    p.add_argument("event", nargs="?", type=parse_date, metavar="YYYY-MM-DD",
                   help="事件日期（--lunar 时按农历解析）")
    p.add_argument("--at", type=parse_date, metavar="YYYY-MM-DD", default=None,
                   help="基准日期，默认今天")
    p.add_argument("--lunar", action="store_true", help="事件日期按农历解析")
    p.add_argument("--leap", action="store_true", help="农历事件为闰月（配合 --lunar）")
    p.add_argument("--selftest", action="store_true", help="运行农历换算自检并退出")
    args = p.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.event is None:
        p.error("缺少事件日期（或使用 --selftest）")
    ref = args.at or date.today()
    try:
        if args.lunar:
            run_lunar(args.event.year, args.event.month, args.event.day,
                      args.leap, ref, args.at is None)
        else:
            run_solar(args.event, ref, args.at is None)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
