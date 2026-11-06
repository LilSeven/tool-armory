#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""儒略日换算：公历日期（可带时刻）与儒略日 JD / 简化儒略日 MJD 双向换算。

用法:
    python julian-day.py to 2000-01-01T12:00:00    # 公历 -> JD / MJD
    python julian-day.py to 2024-06-01             # 省略时刻按 00:00 处理
    python julian-day.py from 2451545.0            # JD -> 公历日期时刻
    python julian-day.py --selftest                # 内置自测

说明:
    - 公历按 proleptic Gregorian 处理，支持公元 1 年至 9999 年；
    - 时刻一律按 UT（世界时）解释，不做时区或ΔT修正；一天从 00:00（JD x.5）起算；
    - MJD = JD - 2400000.5，MJD 0 对应 1858-11-17 00:00 UT；
    - JD/Julian Day 为天文连续纪日，注意与“儒略历”无关。

示例输出:
    $ python julian-day.py to 2000-01-01T12:00:00
    JD  = 2451545.000000
    MJD = 51544.500000
"""

import math
import re
import sys
from datetime import date, timedelta

DAY_SECONDS = 86400.0
_DT_RE = re.compile(
    r"^\s*(-?\d{1,7})-(\d{1,2})-(\d{1,2})"
    r"(?:[T ](\d{1,2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?)?\s*$"
)


def _reconfigure():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def parse_datetime(text):
    """解析 'YYYY-MM-DD[THH:MM[:SS[.fff]]]'，返回 (ordinal, 当日小数天数)。"""
    m = _DT_RE.match(text)
    if not m:
        raise ValueError(
            "日期格式应为 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM[:SS]，收到: %r" % text
        )
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    h = int(m.group(4) or 0)
    mi = int(m.group(5) or 0)
    s = float(m.group(6) or 0.0)
    if h > 24 or mi > 59 or s >= 60.0:
        raise ValueError("时刻超出 00:00:00 ~ 24:00:00 范围: %r" % text)
    ordinal = date(y, mo, d).toordinal()
    frac = (h * 3600 + mi * 60 + s) / DAY_SECONDS
    return ordinal, frac


# RD（ordinal）与儒略日之差：JD 1721424.5 = 公历 0001-01-01 00:00 UT
ORDINAL_TO_JD = 1721424.5


def to_jd(text):
    """公历日期时刻 -> (JD, MJD)。"""
    ordinal, frac = parse_datetime(text)
    jd = ordinal + ORDINAL_TO_JD + frac
    return jd, jd - 2400000.5


def from_jd(jd):
    """JD -> (date, hour, minute, second)。"""
    t = jd - ORDINAL_TO_JD
    day = math.floor(t)
    frac = t - day
    if day < 1 or day > date.max.toordinal():
        raise ValueError("JD 超出支持范围（约公元 1 年 ~ 9999 年）: %r" % jd)
    d = date.fromordinal(int(day))
    secs = round(frac * DAY_SECONDS)
    extra_days, secs = divmod(int(secs), 86400)
    if extra_days:
        d = d + timedelta(days=extra_days)
        if d.toordinal() > date.max.toordinal():
            raise ValueError("JD 超出支持范围（约公元 1 年 ~ 9999 年）: %r" % jd)
    h, rem = divmod(secs, 3600)
    mi, s = divmod(rem, 60)
    return d, h, mi, s


def _fmt_hms(h, mi, s):
    return "%02d:%02d:%06.3f" % (h, mi, s)


def cmd_to(args):
    jd, mjd = to_jd(args[0])
    print("公历   : %s (UT)" % args[0].strip())
    print("JD  = %.6f" % jd)
    print("MJD = %.6f" % mjd)
    return 0


def cmd_from(args):
    jd = float(args[0])
    d, h, mi, s = from_jd(jd)
    print("JD  = %.6f" % jd)
    print("MJD = %.6f" % (jd - 2400000.5))
    print("公历   : %04d-%02d-%02d %s (UT)" % (d.year, d.month, d.day, _fmt_hms(h, mi, s)))
    return 0


def selftest():
    # 已知锚点
    jd, mjd = to_jd("2000-01-01T12:00:00")
    assert abs(jd - 2451545.0) < 1e-9, jd
    assert abs(mjd - 51544.5) < 1e-9, mjd

    jd, mjd = to_jd("1858-11-17")
    assert abs(jd - 2400000.5) < 1e-9, jd
    assert abs(mjd - 0.0) < 1e-9, mjd

    d, h, mi, s = from_jd(2451545.0)
    assert (d.year, d.month, d.day, h, mi, s) == (2000, 1, 1, 12, 0, 0)

    d, h, mi, s = from_jd(2400000.5)
    assert (d.year, d.month, d.day, h, mi, s) == (1858, 11, 17, 0, 0, 0)

    # 双向往返（含小数时刻、闰日、月末）
    samples = [
        "0001-01-01",
        "1582-10-15",
        "1600-02-29",
        "1970-01-01T00:00:00",
        "2000-02-29T23:59:59",
        "2024-06-01T06:30:15.5",
        "9999-12-31T23:59:59",
    ]
    for text in samples:
        jd1, _ = to_jd(text)
        d, h, mi, s = from_jd(jd1)
        jd2 = d.toordinal() + ORDINAL_TO_JD + (h * 3600 + mi * 60 + s) / DAY_SECONDS
        # 反解的秒数四舍五入到整秒，往返误差上限 0.5 秒 ≈ 5.8e-6 天
        assert abs(jd1 - jd2) < 1e-5, (text, jd1, jd2)

    # JD 整数格点落在正午：1920-01-01（ordinal 700900）正午 = JD 2422325.0
    jd, _ = to_jd("1920-01-01T12:00:00")
    assert abs(jd - 2422325.0) < 1e-9, jd
    d, h, mi, s = from_jd(2422325.0)
    assert (d.year, d.month, d.day, h, mi, s) == (1920, 1, 1, 12, 0, 0)
    print("julian-day selftest OK")


def main(argv):
    _reconfigure()
    if argv and argv[0] == "--selftest":
        selftest()
        return 0
    try:
        if len(argv) >= 2 and argv[0] == "to":
            return cmd_to(argv[1:])
        if len(argv) >= 2 and argv[0] == "from":
            return cmd_from(argv[1:])
    except (ValueError, OverflowError) as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 2
    print(__doc__.strip())
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
