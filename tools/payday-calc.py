#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发薪日推算 —— 按“每月 N 号，遇周末提前/顺延/不调整”或“每月最后一天”
规则推算指定年份 12 个发薪日，并标出与名义日的偏差天数。

用法:
    python payday-calc.py 2027
    python payday-calc.py 2027 --day 15 --rule after
    python payday-calc.py 2027 --last --rule before

参数:
    year     推算年份（缺省为当前年份）
    --day N  每月名义发薪日，1-28（默认 10；29-31 在短月不存在，月末请用 --last）
    --rule   遇周末如何调整: before=提前 / after=顺延 / none=不调整（默认 before）
    --last   每月最后一天为名义发薪日（忽略 --day）

示例输出:
    $ python payday-calc.py 2027 --day 10 --rule before
    2027 年发薪日推算（规则: 每月 10 号 · 遇周末提前）
    月份  名义发薪日         实际发薪日         调整
    01月  2027-01-10 周日   2027-01-08 周五   提前 2 天
    02月  2027-02-10 周三   2027-02-10 周三   -
    ...
    全年发薪日 12 个: 提前 X 个, 顺延 Y 个, 周末照发 Z 个

退出码: 0 成功; 2 参数错误（如 --day 超出 1-28）。
仅用 Python 标准库，单文件。
"""

from __future__ import annotations

import argparse
import calendar
import sys
from datetime import date, timedelta

WD_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
RULE_LABEL = {"before": "遇周末提前", "after": "遇周末顺延", "none": "周末不调整"}


def _setup_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def adjust(nom: date, rule: str):
    """把名义日按规则避开周末，返回 (实际日, 相差天数，负=提前 正=顺延)。"""
    if nom.weekday() < 5 or rule == "none":
        return nom, 0
    step = -1 if rule == "before" else 1
    nd = nom
    while nd.weekday() >= 5:
        nd += timedelta(days=step)
    return nd, (nd - nom).days


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="按“每月 N 号遇周末提前/顺延”等规则推算全年发薪日")
    parser.add_argument("year", nargs="?", type=int, help="推算年份（缺省当前年份）")
    parser.add_argument("--day", type=int, default=10, metavar="N",
                        help="每月名义发薪日 1-28（默认 10）")
    parser.add_argument("--rule", choices=["before", "after", "none"], default="before",
                        help="遇周末: before=提前 / after=顺延 / none=不调整（默认 before）")
    parser.add_argument("--last", action="store_true",
                        help="每月最后一天为名义发薪日（忽略 --day）")
    args = parser.parse_args(argv)

    year = args.year if args.year is not None else date.today().year
    if not args.last and not 1 <= args.day <= 28:
        parser.error("--day 需在 1-28（29-31 在短月不存在；月末发薪请用 --last）")

    nominal_label = "每月最后一天" if args.last else f"每月 {args.day} 号"
    print(f"{year} 年发薪日推算（规则: {nominal_label} · {RULE_LABEL[args.rule]}）")
    print("月份  名义发薪日         实际发薪日         调整")

    early = late = keep = 0
    for m in range(1, 13):
        if args.last:
            nom = date(year, m, calendar.monthrange(year, m)[1])
        else:
            nom = date(year, m, args.day)
        actual, delta = adjust(nom, args.rule)
        if delta < 0:
            adj = f"提前 {-delta} 天"
            early += 1
        elif delta > 0:
            adj = f"顺延 {delta} 天"
            late += 1
        elif nom.weekday() >= 5:
            adj = "落周末照发"
            keep += 1
        else:
            adj = "-"
        print(f"{m:02d}月  {nom} {WD_ZH[nom.weekday()]}   "
              f"{actual} {WD_ZH[actual.weekday()]}   {adj}")
    print(f"全年发薪日 12 个: 提前 {early} 个, 顺延 {late} 个, 周末照发 {keep} 个")
    return 0


if __name__ == "__main__":
    _setup_stdio()
    sys.exit(main())
