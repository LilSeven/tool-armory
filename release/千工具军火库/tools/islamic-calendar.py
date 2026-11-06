#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""伊斯兰历换算：公历与 tabular（算术）伊斯兰历互转，标注圣月与斋月开始日期估算。

用法:
    python islamic-calendar.py g2i 2025-03-01    # 公历 -> 伊斯兰历
    python islamic-calendar.py i2g 1446-09-01    # 伊斯兰历(年-月-日) -> 公历
    python islamic-calendar.py ramadan 2025      # 估算 2025 年内的斋月(Ramadan)起始日期
    python islamic-calendar.py --selftest        # 内置自测

说明:
    - 采用 tabular Islamic calendar（回合制 30 年周期，11 闰年），
      以 AH 1 年 1 月 1 日 = 公历 622-07-19（civil epoch）为纪元；
    - 该算法与各地实测观月（新月观测）可能相差 ±1 天，结果为历法估算；
    - 四个圣月（al-ashhur al-hurum）：1 Muharram、7 Rajab、11 Dhu al-Qi'dah、
      12 Dhu al-Hijjah，输出中以【圣月】标注；
    - 斋月为第 9 月 Ramadan，从其 1 日起封斋 29/30 天。

示例输出:
    $ python islamic-calendar.py g2i 2025-03-01
    公历 2025-03-01 = 伊斯兰历 1446-09-01 【斋月首日 Ramadan】
"""

import math
import sys
from datetime import date

ISLAMIC_EPOCH = 227015  # RD 值：AH 1-01-01 = 公历 622-07-19

MONTH_NAMES = {
    1: ("穆哈兰姆月", "Muharram", True),
    2: ("萨法尔月", "Safar", False),
    3: ("赖比月I", "Rabi' al-awwal", False),
    4: ("赖比月II", "Rabi' al-thani", False),
    5: ("哲马达月I", "Jumada al-awwal", False),
    6: ("哲马达月II", "Jumada al-thani", False),
    7: ("赖哲卜月", "Rajab", True),
    8: ("舍尔邦月", "Sha'ban", False),
    9: ("斋月", "Ramadan", False),
    10: ("闪瓦鲁月", "Shawwal", False),
    11: ("祖勒希哲月I", "Dhu al-Qi'dah", True),
    12: ("朝觐月", "Dhu al-Hijjah", True),
}
SACRED_MONTHS = {1, 7, 11, 12}
RAMADAN = 9


def _reconfigure():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _islamic_rd(year, month, day):
    """tabular 公式本体（不做校验）。"""
    return (ISLAMIC_EPOCH - 1 + 354 * (year - 1) + (3 + 11 * year) // 30
            + 29 * (month - 1) + month // 2 + day)


def fixed_from_islamic(year, month, day):
    """伊斯兰历 (year,month,day) -> RD 天数（公历 0001-01-01 = RD 1）。"""
    if not (1 <= month <= 12):
        raise ValueError("月份须为 1~12: %r" % month)
    if month == 12:
        # 闰年（年长 355 天）的 Dhu al-Hijjah 有 30 天
        dim = _islamic_rd(year + 1, 1, 1) - _islamic_rd(year, 12, 1)
    else:
        dim = 30 if month % 2 == 1 else 29
    if not (1 <= day <= dim):
        raise ValueError("日 %r 超出 %d 年 %d 月范围（1~%d）" % (day, year, month, dim))
    return _islamic_rd(year, month, day)


def islamic_from_fixed(rd):
    """RD 天数 -> (year, month, day)。"""
    year = (30 * (rd - ISLAMIC_EPOCH) + 10646) // 10631
    month = min(12, math.ceil((rd - (29 + fixed_from_islamic(year, 1, 1))) / 29.5) + 1)
    day = rd - fixed_from_islamic(year, month, 1) + 1
    return year, month, day


def parse_date(text):
    parts = text.strip().split("-")
    if len(parts) != 3:
        raise ValueError("日期格式应为 YYYY-MM-DD: %r" % text)
    return int(parts[0]), int(parts[1]), int(parts[2])


def _describe(y, m, d):
    cn, en, _ = MONTH_NAMES[m]
    tags = []
    if m in SACRED_MONTHS:
        tags.append("【圣月】")
    if m == RAMADAN:
        tags.append("【斋月首日 Ramadan】" if d == 1 else "【斋月 Ramadan】")
    return "%d年 %s(%s) %d日" % (y, cn, en, d), "".join(tags)


def cmd_g2i(text):
    y, m, d = parse_date(text)
    iy, im, iday = islamic_from_fixed(date(y, m, d).toordinal())
    desc, tags = _describe(iy, im, iday)
    print("公历 %04d-%02d-%02d = 伊斯兰历 %d-%02d-%02d %s%s"
          % (y, m, d, iy, im, iday, desc, tags))
    print("注：tabular 算术历，与实测观月可能相差 ±1 天。")
    return 0


def cmd_i2g(text):
    iy, im, iday = parse_date(text)
    rd = fixed_from_islamic(iy, im, iday)
    g = date.fromordinal(rd)
    desc, tags = _describe(iy, im, iday)
    print("伊斯兰历 %d-%02d-%02d %s = 公历 %04d-%02d-%02d%s"
          % (iy, im, iday, desc, g.year, g.month, g.day, tags))
    return 0


def cmd_ramadan(text):
    """估算给定公历年份内斋月(Ramadan)的起始日期。"""
    gy = int(text.strip())
    jan1 = date(gy, 1, 1).toordinal()
    dec31 = date(gy, 12, 31).toordinal()
    ah_lo = islamic_from_fixed(jan1)[0]
    ah_hi = islamic_from_fixed(dec31)[0]
    found = 0
    for iy in range(ah_lo, ah_hi + 1):
        rd = fixed_from_islamic(iy, RAMADAN, 1)
        if jan1 <= rd <= dec31:
            g = date.fromordinal(rd)
            end = fixed_from_islamic(iy, RAMADAN, 29)
            g_end = date.fromordinal(end)
            print("斋月 Ramadan %d 年：估算自公历 %04d-%02d-%02d 起，"
                  "至 %04d-%02d-%02d（29 天，末日前夕开斋）"
                  % (iy, g.year, g.month, g.day, g_end.year, g_end.month, g_end.day))
            found += 1
    if not found:
        print("%d 年公历范围内未找到斋月开始日期。" % gy)
    print("注：tabular 估算，实际以观月为准，可能相差 ±1 天。")
    return 0


def selftest():
    # 纪元锚点：AH 1-01-01 = 公历 622-07-19
    assert date.fromordinal(fixed_from_islamic(1, 1, 1)) == date(622, 7, 19)
    # 往返逐日（AH 1400-01-01 ~ 1460-12-29，约 60 年）
    rd = fixed_from_islamic(1400, 1, 1)
    end = fixed_from_islamic(1460, 12, 29)
    while rd < end:
        iy, im, iday = islamic_from_fixed(rd)
        assert fixed_from_islamic(iy, im, iday) == rd, (iy, im, iday, rd)
        rd += 1
    # 年长只可能为 354 或 355
    for iy in range(1400, 1460):
        n = fixed_from_islamic(iy + 1, 1, 1) - fixed_from_islamic(iy, 1, 1)
        assert n in (354, 355), n
    # 圣月集合正确
    assert SACRED_MONTHS == {1, 7, 11, 12}
    print("islamic-calendar selftest OK")


def main(argv):
    _reconfigure()
    if argv and argv[0] == "--selftest":
        selftest()
        return 0
    try:
        if len(argv) == 2 and argv[0] == "g2i":
            return cmd_g2i(argv[1])
        if len(argv) == 2 and argv[0] == "i2g":
            return cmd_i2g(argv[1])
        if len(argv) == 2 and argv[0] == "ramadan":
            return cmd_ramadan(argv[1])
    except (ValueError, OverflowError) as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 2
    print(__doc__.strip())
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
