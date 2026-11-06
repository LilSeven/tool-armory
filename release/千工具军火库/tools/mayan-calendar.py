#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""玛雅长纪历换算（纯标准库实现）。

公历日期与玛雅长纪历 baktun/katun/tun/uinal/kin 计数互转。
采用 GMT相关性常数 584283（即 2012-12-21 = 13.0.0.0.0，长纪历纪元起点
0.0.0.0.0 = 公元前 3114 年 8 月 11 日）。公元前日期请用天文纪年法：
公元 1 年为 1，公元前后无 0 年——0 表示公元前 1 年，-1 表示公元前 2 年。

用法：
  python mayan-calendar.py 2012-12-21     公历 -> 长纪历
  python mayan-calendar.py --lc 13.0.0.0.0     长纪历 -> 公历
  python mayan-calendar.py --selftest     内置自测

示例：
  python mayan-calendar.py 2012-12-21   ->  13.0.0.0.0
"""

import argparse
import sys

CORRELATION = 584283  # GMT: JDN = 长纪历天数 + 584283


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


def parse_long_count(text):
    parts = text.strip().split(".")
    if len(parts) != 5:
        raise ValueError("长纪历格式应为 baktun.katun.tun.uinal.kin，如 13.0.0.0.0")
    try:
        nums = [int(x) for x in parts]
    except ValueError:
        raise ValueError("长纪历各段应为整数")
    baktun, katun, tun, uinal, kin = nums
    if not (0 <= baktun <= 19 and 0 <= katun <= 19 and 0 <= tun <= 19
            and 0 <= uinal <= 17 and 0 <= kin <= 19):
        raise ValueError("长纪历数值越界：baktun/katun/tun/kin 0-19，uinal 0-17")
    return baktun * 144000 + katun * 7200 + tun * 360 + uinal * 20 + kin


def long_count_from_jdn(jdn):
    days = jdn - CORRELATION
    if days < 0:
        raise ValueError("该日期早于长纪历纪元起点（0.0.0.0.0）")
    baktun, rem = divmod(days, 144000)
    katun, rem = divmod(rem, 7200)
    tun, rem = divmod(rem, 360)
    uinal, kin = divmod(rem, 20)
    return "%d.%d.%d.%d.%d" % (baktun, katun, tun, uinal, kin)


def format_ymd(y, m, d):
    era = "公元" if y > 0 else "公元前"
    ay = abs(y)
    if y <= 0:
        ay = ay + 1  # 天文纪年 0/-n -> 公元前 1/(n+1) 年
    return "%s%d年%02d月%02d日" % (era, ay, m, d)


def selftest():
    assert jdn_from_ymd(2012, 12, 21) - CORRELATION == 1872000, "13.0.0.0.0 = 2012-12-21"
    assert long_count_from_jdn(jdn_from_ymd(2012, 12, 21)) == "13.0.0.0.0"
    assert long_count_from_jdn(jdn_from_ymd(2012, 12, 20)) == "12.19.19.17.19"
    assert long_count_from_jdn(jdn_from_ymd(2012, 12, 22)) == "13.0.0.0.1"
    # 纪元起点 = 公元前 3114 年 8 月 11 日（天文纪年 -3113）
    y, m, d = ymd_from_jdn(CORRELATION)
    assert (y, m, d) == (-3113, 8, 11), (y, m, d)
    # 双向往返
    for jdn in (CORRELATION, jdn_from_ymd(1, 1, 1), jdn_from_ymd(2000, 1, 1),
                jdn_from_ymd(3000, 1, 1)):
        lc = long_count_from_jdn(jdn)
        assert parse_long_count(lc) + CORRELATION == jdn, lc
    print("selftest OK")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="公历与玛雅长纪历互转（相关性 584283）")
    p.add_argument("date", nargs="?", help="公历日期 YYYY-MM-DD（公元前用天文纪年，如 -3113-08-11）")
    p.add_argument("--lc", metavar="计数", help='长纪历计数，如 "13.0.0.0.0"')
    p.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = p.parse_args(argv)

    if args.selftest:
        selftest()
        return
    if args.lc:
        days = parse_long_count(args.lc)
        jdn = days + CORRELATION
        y, m, d = ymd_from_jdn(jdn)
        print("长纪历 %s = 公历 %s（儒略日数 %d）" % (args.lc, format_ymd(y, m, d), jdn))
        return
    if not args.date:
        p.error("请提供公历日期 YYYY-MM-DD 或 --lc 长纪历计数")
    try:
        y, m, d = (int(x) for x in args.date.split("-"))
    except ValueError:
        p.error("日期格式应为 YYYY-MM-DD")
    jdn = jdn_from_ymd(y, m, d)
    try:
        lc = long_count_from_jdn(jdn)
    except ValueError as exc:
        p.error(str(exc))
    print("公历 %s = 长纪历 %s（儒略日数 %d）"
          % (format_ymd(y, m, d), lc, jdn))


if __name__ == "__main__":
    main()
