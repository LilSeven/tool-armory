#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""儒略历日期换算：公历（格里历）与儒略历日期互转，用于历史事件日期对照。

用法:
    python julian-calendar.py g2j 1917-11-07    # 公历 -> 儒略历
    python julian-calendar.py j2g 1917-10-25    # 儒略历 -> 公历
    python julian-calendar.py --selftest        # 内置自测

说明:
    - 儒略历（Julian calendar）：每 4 年一闰，由凯撒于公元前 45 年启用；
    - 两历差异随世纪累积：1582-10-15（公历）对应儒略历 1582-10-05，相差 10 天；
      1900-03-13 ~ 2100-02-28 期间相差 13 天；
    - 1582-10-05 ~ 1582-10-14（公历）在历史上不存在（教皇格里高利十三世删除）；
    - 1582 年以前的日期按各自的历法规则向后（proleptic）外推，
      古代事件换算结果仅为历法对照，不含当年纪年/岁首差异。

示例输出:
    $ python julian-calendar.py g2j 1917-11-07
    公历(格里历) 1917-11-07 = 儒略历 1917-10-25 （相差 13 天）
"""

import sys
from datetime import date

JULIAN_EPOCH = -1  # 儒略历纪元（RD 值），儒略历公元 1-01-01 = RD 0
MONTH_LEN = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def _reconfigure():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def julian_leap(year):
    return year % 4 == 0


def fixed_from_julian(y, m, d):
    """儒略历 (y,m,d) -> RD 天数（公历 0001-01-01 = RD 1，与 date.toordinal 一致）。"""
    if not (1 <= m <= 12):
        raise ValueError("月份须为 1~12: %r" % m)
    dim = MONTH_LEN[m - 1] + (1 if (m == 2 and julian_leap(y)) else 0)
    if not (1 <= d <= dim):
        raise ValueError("日 %r 超出 %d 年 %d 月范围" % (d, y, m))
    y0 = y - 1
    c = (367 * m - 362) // 12
    if m > 2:
        c += -1 if julian_leap(y) else -2
    return JULIAN_EPOCH - 1 + 365 * y0 + y0 // 4 + c + d


def julian_from_fixed(rd):
    """RD 天数 -> 儒略历 (y,m,d)。"""
    y = (4 * (rd - JULIAN_EPOCH) + 1464) // 1461
    while fixed_from_julian(y, 1, 1) > rd:
        y -= 1
    while fixed_from_julian(y + 1, 1, 1) <= rd:
        y += 1
    rem = rd - fixed_from_julian(y, 1, 1)
    for m in range(1, 13):
        dim = MONTH_LEN[m - 1] + (1 if (m == 2 and julian_leap(y)) else 0)
        if rem < dim:
            return y, m, rem + 1
        rem -= dim
    raise AssertionError("unreachable")


def parse_date(text):
    parts = text.strip().split("-")
    if len(parts) != 3:
        raise ValueError("日期格式应为 YYYY-MM-DD: %r" % text)
    return int(parts[0]), int(parts[1]), int(parts[2])


def gregorian_to_julian(y, m, d):
    rd = date(y, m, d).toordinal()
    return julian_from_fixed(rd), rd


def julian_to_gregorian(y, m, d):
    rd = fixed_from_julian(y, m, d)
    if rd < 1:
        raise ValueError("结果早于公元 1 年，超出支持范围")
    g = date.fromordinal(rd)
    return (g.year, g.month, g.day), rd


def _calendar_gap(jy, jm, jd, rd):
    """两历标签的天数差：同一 RD 上，儒略历标签按公历解读的序数之差。"""
    try:
        return rd - date(jy, jm, jd).toordinal()
    except (ValueError, OverflowError):
        return None


def cmd_g2j(text):
    y, m, d = parse_date(text)
    (jy, jm, jd), rd = gregorian_to_julian(y, m, d)
    gap = _calendar_gap(jy, jm, jd, rd)
    tail = " （相差 %d 天）" % gap if gap is not None else ""
    print("公历(格里历) %04d-%02d-%02d = 儒略历 %04d-%02d-%02d%s"
          % (y, m, d, jy, jm, jd, tail))
    return 0


def cmd_j2g(text):
    y, m, d = parse_date(text)
    (gy, gm, gd), rd = julian_to_gregorian(y, m, d)
    gap = _calendar_gap(y, m, d, rd)
    tail = " （相差 %d 天）" % gap if gap is not None else ""
    print("儒略历 %04d-%02d-%02d = 公历(格里历) %04d-%02d-%02d%s"
          % (y, m, d, gy, gm, gd, tail))
    return 0


def selftest():
    # 俄国十月革命：儒略历 1917-10-25 = 公历 1917-11-07
    assert julian_to_gregorian(1917, 10, 25)[0] == (1917, 11, 7)
    assert gregorian_to_julian(1917, 11, 7)[0] == (1917, 10, 25)
    # 格里历改革首日：公历 1582-10-15 = 儒略历 1582-10-05
    assert gregorian_to_julian(1582, 10, 15)[0] == (1582, 10, 5)
    assert julian_to_gregorian(1582, 10, 5)[0] == (1582, 10, 15)
    # 儒略历 2000-01-01 = 公历 2000-01-14（相差 13 天）
    assert julian_to_gregorian(2000, 1, 1)[0] == (2000, 1, 14)
    assert gregorian_to_julian(2000, 1, 14)[0] == (2000, 1, 1)
    # 儒略历闰年：2100 年儒略历仍闰（公历不闰），儒略历 2100-02-29 = 公历 2100-03-14
    assert julian_leap(2100)
    assert julian_to_gregorian(2100, 2, 29)[0] == (2100, 3, 14)
    # 双向往返（儒略历连续区间逐日）
    rd = fixed_from_julian(1800, 1, 1)
    end = fixed_from_julian(2200, 1, 1)
    while rd < end:
        jy, jm, jd = julian_from_fixed(rd)
        assert fixed_from_julian(jy, jm, jd) == rd, (jy, jm, jd, rd)
        rd += 1
    print("julian-calendar selftest OK")


def main(argv):
    _reconfigure()
    if argv and argv[0] == "--selftest":
        selftest()
        return 0
    try:
        if len(argv) == 2 and argv[0] == "g2j":
            return cmd_g2j(argv[1])
        if len(argv) == 2 and argv[0] == "j2g":
            return cmd_j2g(argv[1])
    except (ValueError, OverflowError) as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 2
    print(__doc__.strip())
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
