#!/usr/bin/env python3
"""工作日间隔统计 —— 统计两日期之间的工作日数量，分别列出排除的周末与节假日。

统计区间为闭区间 [start, end]（含两端）; 若开始日期晚于结束日期则自动交换并提示。
归类优先级: 调休补班日 > 节假日 > 周末 > 普通工作日，
即落在周末的法定节假日计入「节假日」，不在「周末」中重复统计。

用法示例:
    python workday-diff.py --start 2025-10-01 --end 2025-10-15 --holidays 2025-10-01,2025-10-02,2025-10-03,2025-10-04,2025-10-05,2025-10-06,2025-10-07,2025-10-08
    python workday-diff.py --start 2025-11-01 --end 2025-11-30
"""

import argparse
import sys
from datetime import date, timedelta

WEEKDAY_ZH = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
MAX_SPAN_DAYS = 100000
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


def classify(day, holidays, makeup):
    """单日归类: work / holiday / weekend / makeup。"""
    if day in makeup:
        return "makeup"
    if day in holidays:
        return "holiday"
    if day.weekday() >= 5:
        return "weekend"
    return "work"


def main(argv=None):
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="统计两日期之间的工作日数量，分别列出排除的周末与节假日")
    parser.add_argument("--start", type=parse_date, required=True, metavar="YYYY-MM-DD",
                        help="开始日期")
    parser.add_argument("--end", type=parse_date, required=True, metavar="YYYY-MM-DD",
                        help="结束日期（含当日）")
    parser.add_argument("--holidays", type=parse_date_set, default=set(),
                        metavar="D1,D2,...", help="节假日列表（逗号分隔）")
    parser.add_argument("--workdays", type=parse_date_set, default=set(),
                        metavar="D1,D2,...", help="调休补班日列表（逗号分隔）")
    parser.add_argument("--limit", type=int, default=MAX_LIST, metavar="N",
                        help="每类明细最多列出的条数（默认 %d）" % MAX_LIST)
    args = parser.parse_args(argv)

    if args.limit < 0:
        parser.error("--limit 不能为负数")

    start, end = args.start, args.end
    if start > end:
        start, end = end, start
        print("提示: 开始日期晚于结束日期，已自动交换")
    if (end - start).days > MAX_SPAN_DAYS:
        parser.error("区间跨度过大（上限 %d 天）" % MAX_SPAN_DAYS)

    buckets = {"work": [], "makeup": [], "holiday": [], "weekend": []}
    day = start
    while day <= end:
        buckets[classify(day, args.holidays, args.workdays)].append(day)
        day += timedelta(days=1)

    total = (end - start).days + 1
    print("区间: %s（%s）~ %s（%s），共 %d 天"
          % (start.isoformat(), WEEKDAY_ZH[start.weekday()],
             end.isoformat(), WEEKDAY_ZH[end.weekday()], total))
    print("工作日: %d 天（普通 %d + 调休补班 %d）"
          % (len(buckets["work"]) + len(buckets["makeup"]),
             len(buckets["work"]), len(buckets["makeup"])))

    def dump(title, days):
        if not days:
            print("%s: 0 天" % title)
            return
        shown = days[:args.limit]
        extra = len(days) - len(shown)
        detail = " ".join("%s(%s)" % (d.isoformat(), WEEKDAY_ZH[d.weekday()])
                          for d in shown)
        tail = " ……另有 %d 天未列出" % extra if extra > 0 else ""
        print("%s: %d 天: %s%s" % (title, len(days), detail, tail))

    dump("排除 - 节假日", buckets["holiday"])
    dump("排除 - 周末", buckets["weekend"])
    if buckets["makeup"]:
        dump("计入 - 调休补班", buckets["makeup"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
