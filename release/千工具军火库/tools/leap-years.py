#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闰年判断列举:判断某年是否闰年并按规则解释;或列出给定区间内全部闰年。

格里高利历闰年规则:能被 4 整除且不能被 100 整除;或能被 400 整除。闰年 366 天。

示例命令:
  python leap-years.py 2024        # 判断 2024(闰年,能被 4 整除且不被 100 整除)
  python leap-years.py 1900        # 世纪年:1900 是平年(被 100 整除但不被 400 整除)
  python leap-years.py 2000 2050   # 列出 2000~2050 年间的全部闰年
"""

import argparse
import calendar
import sys

LEAP_RULE = "格里高利历规则:能被 4 整除且不被 100 整除,或能被 400 整除,为闰年"


def explain(year):
    """按整除情形给出带解释的结论。"""
    if year % 400 == 0:
        return "闰年(%d 能被 400 整除),全年 366 天" % year
    if year % 100 == 0:
        return "平年(%d 能被 100 整除但不能被 400 整除),全年 365 天" % year
    if year % 4 == 0:
        return "闰年(%d 能被 4 整除且不被 100 整除),全年 366 天" % year
    return "平年(%d 不能被 4 整除),全年 365 天" % year


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        description="判断闰年并按规则解释,或列出区间内全部闰年")
    parser.add_argument("years", nargs="+", type=int,
                        help="给 1 个年份=判断该年;给 2 个年份=列出区间内的闰年")
    args = parser.parse_args(argv)

    if len(args.years) == 1:
        y = args.years[0]
        if not 1 <= y <= 9999:
            parser.error("年份须在 1~9999 之间")
        verdict = explain(y)
        # 与标准库 calendar.isleap 交叉校验(不可达分支,防御性检查)
        if verdict.startswith("闰年") != calendar.isleap(y):
            parser.error("内部计算不一致:%s 与 calendar.isleap(%d) 矛盾" % (verdict, y))
        print("%d 年是%s" % (y, verdict))
        print(LEAP_RULE)
    elif len(args.years) == 2:
        a, b = sorted(args.years)
        if not (1 <= a and b <= 9999):
            parser.error("年份须在 1~9999 之间")
        span = b - a + 1
        if span > 3000:
            parser.error("区间跨度最多 3000 年,请缩小范围")
        leaps = [y for y in range(a, b + 1) if calendar.isleap(y)]
        print("%d~%d 年间(共 %d 年)有 %d 个闰年:" % (a, b, span, len(leaps)))
        for i in range(0, len(leaps), 12):
            print("  " + ", ".join("%d" % y for y in leaps[i:i + 12]))
        if not leaps:
            print("  (无)")
    else:
        parser.error("最多给 2 个年份:1 个为判断,2 个为区间列举")
    return 0


if __name__ == "__main__":
    sys.exit(main())
