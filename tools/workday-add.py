#!/usr/bin/env python3
"""工作日加减推算 —— 从给定日期向前/向后推 N 个工作日。

默认按「周一至周五为工作日，周六日为休息日」推算:
  --holidays 指定额外节假日（即使逢工作日也跳过）;
  --workdays 指定调休补班日（即使逢周末也计入工作日）。
天数 N 为负表示向过去方向推算，N=0 时原地返回起始日期。

用法示例:
    python workday-add.py --date 2025-09-30 --days 3
    python workday-add.py --days -5
    python workday-add.py --date 2025-09-30 --days 3 --holidays 2025-10-01,2025-10-02,2025-10-03,2025-10-04,2025-10-05,2025-10-06,2025-10-07,2025-10-08
"""

import argparse
import sys
from datetime import date, timedelta

WEEKDAY_ZH = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
MAX_DAYS = 100000
MAX_LIST = 50


def _force_utf8_stdio():
    """让输出在 Windows 管道/重定向下也按 UTF-8 编码（Git Bash 友好）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_date(text):
    """解析 YYYY-MM-DD 日期。"""
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError("日期格式应为 YYYY-MM-DD，收到 %r" % text)


def parse_date_set(text):
    """解析逗号分隔的日期列表为集合。"""
    result = set()
    for token in text.split(","):
        token = token.strip()
        if token:
            result.add(parse_date(token))
    return result


def is_workday(day, holidays, makeup):
    """判断某日是否为工作日: 补班日 > 节假日 > 周末规则。"""
    if day in makeup:
        return True
    if day in holidays:
        return False
    return day.weekday() < 5


def skip_reason(day, holidays):
    return "节假日" if day in holidays else "周末"


def add_workdays(start, n, holidays, makeup):
    """从 start 起推 n 个工作日，返回 (结果日期, 沿途跳过的非工作日列表)。"""
    step = 1 if n >= 0 else -1
    remaining = abs(n)
    day = start
    skipped = []
    while remaining > 0:
        day += timedelta(days=step)
        if is_workday(day, holidays, makeup):
            remaining -= 1
        else:
            skipped.append(day)
    return day, skipped


def main(argv=None):
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="从给定日期向前/向后推 N 个工作日（支持节假日与调休补班表）")
    parser.add_argument("--date", type=parse_date, default=None, metavar="YYYY-MM-DD",
                        help="起始日期（默认今天）")
    parser.add_argument("--days", type=int, required=True, metavar="N",
                        help="推算的工作日天数，负数表示向过去方向")
    parser.add_argument("--holidays", type=parse_date_set, default=set(),
                        metavar="D1,D2,...", help="节假日列表（逗号分隔）")
    parser.add_argument("--workdays", type=parse_date_set, default=set(),
                        metavar="D1,D2,...", help="调休补班日列表（逗号分隔）")
    args = parser.parse_args(argv)

    if abs(args.days) > MAX_DAYS:
        parser.error("--days 绝对值过大（上限 %d）" % MAX_DAYS)

    start = args.date if args.date is not None else date.today()
    result, skipped = add_workdays(start, args.days, args.holidays, args.workdays)

    sign = "+" if args.days >= 0 else "-"
    print("起始: %s（%s）" % (start.isoformat(), WEEKDAY_ZH[start.weekday()]))
    print("推算: %s%d 个工作日 -> %s（%s）"
          % (sign, abs(args.days), result.isoformat(), WEEKDAY_ZH[result.weekday()]))
    if args.days == 0:
        print("说明: 天数为 0，原地返回起始日期")
    elif skipped:
        shown = skipped[:MAX_LIST]
        extra = len(skipped) - len(shown)
        detail = " ".join("%s(%s)" % (d.isoformat(), skip_reason(d, args.holidays))
                          for d in shown)
        tail = " ……另有 %d 天未列出" % extra if extra > 0 else ""
        print("沿途跳过 %d 个非工作日: %s%s" % (len(skipped), detail, tail))
    else:
        print("沿途无跳过的非工作日")
    return 0


if __name__ == "__main__":
    sys.exit(main())
