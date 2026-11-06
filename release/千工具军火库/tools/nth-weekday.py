#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第 N 个星期几计算（nth-weekday）。

求某月第 n 个星期几的日期（例如 2026 年 5 月第 2 个周日 = 2026-05-10，
即母亲节），支持一次批量计算多个月份；n 取 last / -1 表示当月最后一个。

用法:
    python nth-weekday.py YEAR NTH WEEKDAY [--months 5,6,7 | 1-12 | all] [-v]

参数:
    YEAR     年份，如 2026
    NTH      第几个：正整数，或 last / -1（当月最后一个）
    WEEKDAY  星期几：mon/tue/wed/thu/fri/sat/sun（大小写随意），或
             0-6（0=周一 … 6=周日），或汉字 一/二/三/四/五/六/日/天

选项:
    -m, --months LIST  月份列表，逗号分隔，支持 a-b 区间；缺省为全年 12 个月
    -v, --verbose      每行附带说明列
    -h, --help         显示帮助

示例命令:
    python nth-weekday.py 2026 2 sun -m 5
    python nth-weekday.py 2026 1 mon -m 1-12
    python nth-weekday.py 2026 last fri -m 4,6,9 -v

输出: 每行一个 ISO 日期（YYYY-MM-DD），按月份升序。
若某月不存在该序数（如该月只有 4 个周日却要第 5 个），跳过该月、
向 stderr 打印提示，整体退出码仍为 0；参数错误退出码为 2。

仅使用 Python 标准库。
"""

from __future__ import annotations

import argparse
import calendar
import re
import sys
from datetime import date, timedelta

EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

WD = {
    "mon": 0, "monday": 0, "一": 0, "周一": 0, "星期一": 0,
    "tue": 1, "tuesday": 1, "二": 1, "周二": 1, "星期二": 1,
    "wed": 2, "wednesday": 2, "三": 2, "周三": 2, "星期三": 2,
    "thu": 3, "thursday": 3, "四": 3, "周四": 3, "星期四": 3,
    "fri": 4, "friday": 4, "五": 4, "周五": 4, "星期五": 4,
    "sat": 5, "saturday": 5, "六": 5, "周六": 5, "星期六": 5,
    "sun": 6, "sunday": 6, "日": 6, "天": 6, "周日": 6, "星期日": 6, "周天": 6, "星期天": 6,
}


def parse_weekday(s: str) -> int:
    t = s.strip().lower()
    if t in WD:
        return WD[t]
    if re.fullmatch(r"[0-6]", t):
        return int(t)
    raise argparse.ArgumentTypeError(
        f"无法识别的星期几: {s!r}（可用 mon..sun、0-6（0=周一）或汉字 一/…/日）")


def parse_months(s: str) -> list:
    months = set()
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if part.lower() in ("all", "全年"):
            months.update(range(1, 13))
            continue
        m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if not (1 <= a <= 12 and 1 <= b <= 12) or a > b:
                raise argparse.ArgumentTypeError(f"非法月份区间: {part}")
            months.update(range(a, b + 1))
        elif part.isdigit() and 1 <= int(part) <= 12:
            months.add(int(part))
        else:
            raise argparse.ArgumentTypeError(f"非法月份: {part}")
    if not months:
        raise argparse.ArgumentTypeError("月份列表为空")
    return sorted(months)


def nth_weekday_of_month(year: int, month: int, wd: int, nth: int):
    """返回该月第 nth 个 wd 星期几的 date；不存在返回 None。nth=-1 表示最后一个。"""
    if nth == -1:
        last_day = calendar.monthrange(year, month)[1]
        d = date(year, month, last_day)
        return d - timedelta(days=(d.weekday() - wd) % 7)
    first = date(year, month, 1)
    d = first + timedelta(days=(wd - first.weekday()) % 7 + 7 * (nth - 1))
    return d if d.month == month else None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nth-weekday",
        description="求某月第 n 个星期几（支持批量多月份；n=last 表示当月最后一个）。",
    )
    p.add_argument("year", type=int, help="年份，如 2026")
    p.add_argument("nth", help="第几个：正整数，或 last / -1")
    p.add_argument("weekday", type=parse_weekday,
                   help="星期几：mon..sun / 0-6（0=周一）/ 汉字 一..日")
    p.add_argument("-m", "--months", default="1-12", type=parse_months,
                   help="月份列表，如 5,6,7 或 1-12（缺省全年）")
    p.add_argument("-v", "--verbose", action="store_true", help="输出附带说明列")
    return p


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args = build_parser().parse_args(argv)

    if not (1 <= args.year <= 9999):
        print(f"错误: 年份超出范围: {args.year}", file=sys.stderr)
        return 2

    nth_text = str(args.nth).strip().lower()
    if nth_text in ("last", "-1"):
        nth, nth_label = -1, "最后一个"
    else:
        try:
            nth = int(nth_text)
        except ValueError:
            print(f"错误: 非法序数 {args.nth!r}（应为正整数或 last/-1）", file=sys.stderr)
            return 2
        if not 1 <= nth <= 53:
            print(f"错误: 序数超出范围: {nth}", file=sys.stderr)
            return 2
        nth_label = f"第{nth}个"

    for m in args.months:
        d = nth_weekday_of_month(args.year, m, args.weekday, nth)
        if d is None:
            print(f"提示: {args.year}-{m:02d} 不存在{nth_label} "
                  f"{EN[args.weekday]}", file=sys.stderr)
            continue
        if args.verbose:
            print(f"{d.isoformat()}  # {args.year}-{m:02d} {nth_label} {EN[args.weekday]}")
        else:
            print(d.isoformat())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
