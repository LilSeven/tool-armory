#!/usr/bin/env python3
"""复活节及 movable 节日日期计算（Gauss / 匿名儒略算法）。

使用 Anonymous Gregorian algorithm（Meeus/Jones/Butcher，即高斯算法的
现代修正版，对 1583 年后所有年份正确）计算西方教会复活节（Gregorian
Easter），并派生相关 movable 节日：
    - 圣枝主日 Palm Sunday      = 复活节 - 7 天
    - 耶稣升天节 Ascension      = 复活节 + 39 天
    - 圣灵降临节 Pentecost      = 复活节 + 49 天
    - 三一主日 Trinity Sunday   = 复活节 + 56 天
另支持 --julian 计算儒略历复活节（东正教），并可选 --julian-to-greg
把结果换算成公历日期。

仅用 Python 标准库，单文件。

示例命令：
    python -I easter-date.py 2026
    python -I easter-date.py 2026 --julian --julian-to-greg
    python -I easter-date.py 1990-2100 --range
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import sys

DERIVED = [
    ("圣枝主日 Palm Sunday", -7),
    ("复活节 Easter Sunday", 0),
    ("耶稣升天节 Ascension Day", 39),
    ("圣灵降临节 Pentecost", 49),
    ("三一主日 Trinity Sunday", 56),
]


def gregorian_easter(year: int) -> dt.date:
    """Anonymous Gregorian algorithm（Meeus/Jones/Butcher）。适用 1583+。"""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(year, month, day)


def julian_easter(year: int) -> dt.date:
    """儒略历复活节（Meeus 的 Julian algorithm），日期为儒略历日期。"""
    a = year % 4
    b = year % 7
    c = year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = (d + e + 114) % 31 + 1
    return dt.date(year, month, day)


def julian_to_gregorian(y: int, m: int, d: int) -> dt.date:
    """把儒略历日期换算为公历日期（Meeus 儒略历→JDN→格里高利）。"""
    # 儒略历日期 -> JDN
    a = (14 - m) // 12
    y2 = y + 4800 - a
    m2 = m + 12 * a - 3
    jdn = d + (153 * m2 + 2) // 5 + 365 * y2 + y2 // 4 - 32083
    # JDN -> 公历（标准格里高利换算）
    a = jdn + 32044
    b = (4 * a + 3) // 146097
    c = a - 146097 * b // 4
    dd = (4 * c + 3) // 1461
    e = c - 1461 * dd // 4
    mm = (5 * e + 2) // 153
    day = e - (153 * mm + 2) // 5 + 1
    month = mm + 3 - 12 * (mm // 10)
    year = 100 * b + dd - 4800 + mm // 10
    return dt.date(year, month, day)


def fmt2(date: dt.date) -> str:
    wd = "一二三四五六日"[date.weekday()]
    return f"{date.isoformat()} 周{wd}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="计算复活节及相关 movable 节日")
    ap.add_argument("years", nargs="+",
                    help="年份，可给多个；配合 --range 时给 起-止 两值，"
                         "或用单参数区间形式 '起-止'（如 1990-2100）")
    ap.add_argument("--range", action="store_true",
                    help="按区间逐年输出复活节；区间可写作 '1990 2100 --range'"
                         " 或 '1990-2100 --range'")
    ap.add_argument("--julian", action="store_true", help="计算儒略历（东正教）复活节")
    ap.add_argument("--julian-to-greg", action="store_true", help="把儒略历结果换算为公历日期")
    ns = ap.parse_args(argv)

    # --range 支持 '起-止' 单参数写法
    if ns.range and len(ns.years) == 1 and "-" in ns.years[0]:
        try:
            a, b = ns.years[0].split("-", 1)
            ns.years = [a, b]
        except ValueError:
            pass

    try:
        years = [int(y) for y in ns.years]
    except ValueError:
        hint = ""
        if any("-" in y for y in ns.years):
            hint = "（若想表达年份区间，请加 --range，如 easter-date.py 1990-2100 --range）"
        print(f"错误：年份必须是整数{hint}", file=sys.stderr)
        return 2

    if ns.range:
        if len(years) != 2 or years[0] > years[1]:
            print("错误：--range 需要 起-止 两个升序年份，或单参数 '起-止' 形式",
                  file=sys.stderr)
            return 2
        years = list(range(years[0], years[1] + 1))

    for y in years:
        if not (1 <= y <= 9999):
            print(f"错误：年份 {y} 超出支持范围 1-9999", file=sys.stderr)
            return 2
        if not ns.julian and y < 1583:
            print(f"警告：{y} 年早于 1583，格里高利复活节算法不适用，结果仅供参考",
                  file=sys.stderr)
        if ns.julian:
            easter = julian_easter(y)
            label = "儒略历复活节"
            if ns.julian_to_greg:
                g = julian_to_gregorian(easter.year, easter.month, easter.day)
                print(f"{y} 年 {label}（儒略历）: {easter.isoformat()}"
                      f" = 公历 {fmt2(g)}")
                for name, off in DERIVED[1:]:
                    print(f"    {name}（公历）: {fmt2(g + dt.timedelta(days=off))}")
            else:
                print(f"{y} 年 {label}: {easter.isoformat()}")
                for name, off in DERIVED[1:]:
                    print(f"    {name}: {easter + dt.timedelta(days=off):%Y-%m-%d}")
        else:
            easter = gregorian_easter(y)
            print(f"{y} 年复活节: {fmt2(easter)}")
            for name, off in DERIVED:
                if off == 0:
                    continue
                print(f"    {name}: {fmt2(easter + dt.timedelta(days=off))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
