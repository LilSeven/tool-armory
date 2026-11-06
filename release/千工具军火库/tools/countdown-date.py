#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日期倒计时 —— 计算距离目标日期的总天数、剩余周数和工作日天数。

用法:
    python countdown-date.py 2027-01-01                        # 以今天为基准
    python countdown-date.py 2027-01-01 --from 2026-11-02      # 指定基准日期
    python countdown-date.py 2027-01-01 --holidays 2026-12-25,2027-01-01

说明:
    工作日 = 基准日之后(不含基准日)、目标日当天(含)之间，周一至周五
    且不在 --holidays 列表中的日子；落在周末的节假日不重复扣减。

示例输出:
    $ python countdown-date.py 2026-12-31 --from 2026-11-02
    基准日期: 2026-11-02 (星期一)
    目标日期: 2026-12-31 (星期四)
    总天数  : 59 天
    剩余周数: 8 周 3 天 (约 8.4 周)
    工作日  : 43 天 (已跳过 16 个周末日)

退出码: 0 成功(含目标日已过去的情况); 2 参数或日期格式错误。
仅用 Python 标准库。
"""

import argparse
import sys
from datetime import date, timedelta

ZH_WD = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def parse_date(text):
    """解析 YYYY-MM-DD 或 today/tomorrow，失败抛 ValueError。"""
    t = text.strip().lower()
    if t == "today":
        return date.today()
    if t == "tomorrow":
        return date.today() + timedelta(days=1)
    return date.fromisoformat(t)


def count_workdays(base, target, holidays):
    """统计 (base, target] 区间内的工作日，返回 (工作日, 周末日, 落在工作日的节假日数)。"""
    work = weekend = holiday = 0
    d = base + timedelta(days=1)
    while d <= target:
        if d.weekday() >= 5:
            weekend += 1
        elif d in holidays:
            holiday += 1
        else:
            work += 1
        d += timedelta(days=1)
    return work, weekend, holiday


def main(argv=None):
    p = argparse.ArgumentParser(description="计算距离目标日期的天数/周数/工作日天数")
    p.add_argument("target", help="目标日期 YYYY-MM-DD (或 today/tomorrow)")
    p.add_argument("--from", dest="base", default=None,
                   help="基准日期 YYYY-MM-DD, 默认今天")
    p.add_argument("--holidays", default="",
                   help="逗号分隔的节假日列表 YYYY-MM-DD (仅周一至周五的会扣减工作日)")
    args = p.parse_args(argv)

    try:
        holidays = {parse_date(x) for x in args.holidays.split(",") if x.strip()}
    except ValueError as e:
        print(f"错误: --holidays 日期无效: {e}", file=sys.stderr)
        return 2
    try:
        base = parse_date(args.base) if args.base else date.today()
        target = parse_date(args.target)
    except ValueError as e:
        print(f"错误: 日期无效: {e}", file=sys.stderr)
        return 2

    days = (target - base).days
    print(f"基准日期: {base.isoformat()} ({ZH_WD[base.weekday()]})")
    print(f"目标日期: {target.isoformat()} ({ZH_WD[target.weekday()]})")
    if days < 0:
        print(f"目标已过去: {-days} 天")
        return 0
    print(f"总天数  : {days} 天")
    weeks, rem = divmod(days, 7)
    print(f"剩余周数: {weeks} 周 {rem} 天 (约 {days / 7:.1f} 周)")
    work, weekend, holiday = count_workdays(base, target, holidays)
    extra = f"、{holiday} 个节假日" if holiday else ""
    print(f"工作日  : {work} 天 (已跳过 {weekend} 个周末日{extra})")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
