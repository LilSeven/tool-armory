#!/usr/bin/env python3
"""敏捷迭代日历（sprint-calendar）

用途：
    给定起始日与迭代长度（工作日天数），连续生成若干个 Sprint 的
    起止日期与工作日清单。默认跳过周六周日，可用 --holidays 排除
    节假日；用 --include-weekends 则按自然日（含周末）排迭代。

参数：
    --start             Sprint 1 的起始日 YYYY-MM-DD（默认今天）
    --length            每个 Sprint 的工作日天数（默认 10）
    --sprints           生成多少个 Sprint（默认 1）
    --holidays          逗号分隔的节假日 YYYY-MM-DD，不计为工作日
    --include-weekends  周六周日也计入工作日
    --no-days           只输出每个 Sprint 的起止，不逐日列出清单

示例命令：
    python sprint-calendar.py --start 2026-11-02 --length 10 --sprints 3
    python sprint-calendar.py --start 2026-11-02 --length 5 --sprints 2 --holidays 2026-11-20
    python sprint-calendar.py --start 2026-11-02 --length 14 --include-weekends --no-days
"""

import argparse
import sys
from datetime import date, datetime, timedelta

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _setup_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_dates(text):
    out = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        out.add(datetime.strptime(part, "%Y-%m-%d").date())
    return out


def main(argv=None):
    _setup_stdout()
    parser = argparse.ArgumentParser(
        description="按迭代长度生成 Sprint 起止日期与工作日清单",
        epilog="示例: python sprint-calendar.py --start 2026-11-02 --length 10 --sprints 3",
    )
    parser.add_argument("--start", help="Sprint 1 起始日 YYYY-MM-DD（默认今天）")
    parser.add_argument("--length", type=int, default=10,
                        help="每个 Sprint 的工作日天数（默认 10）")
    parser.add_argument("--sprints", type=int, default=1,
                        help="生成多少个 Sprint（默认 1）")
    parser.add_argument("--holidays", default="",
                        help="逗号分隔的节假日 YYYY-MM-DD，不计为工作日")
    parser.add_argument("--include-weekends", action="store_true",
                        help="周六周日也计入工作日")
    parser.add_argument("--no-days", action="store_true",
                        help="不逐日列出工作日清单")
    args = parser.parse_args(argv)

    if args.length < 1:
        parser.error("--length 至少为 1")
    if args.sprints < 1:
        parser.error("--sprints 至少为 1")
    try:
        start = (datetime.strptime(args.start, "%Y-%m-%d").date()
                 if args.start else date.today())
        holidays = parse_dates(args.holidays)
    except ValueError:
        parser.error("日期格式应为 YYYY-MM-DD（--start / --holidays）")

    skip_weekend = not args.include_weekends
    cursor = start
    total = 0
    for s in range(1, args.sprints + 1):
        days = []
        d = cursor
        limit = cursor + timedelta(days=3660)
        while len(days) < args.length:
            if d > limit:
                parser.error("10 年内凑不齐 %d 个工作日，请检查 --holidays 设置" % args.length)
            if (not skip_weekend or d.weekday() < 5) and d not in holidays:
                days.append(d)
            d += timedelta(days=1)
        total += len(days)
        first, last = days[0], days[-1]
        print("Sprint %d: %s（%s）→ %s（%s）｜ 工作日 %d 天" % (
            s,
            first.strftime("%Y-%m-%d"), WEEKDAY_CN[first.weekday()],
            last.strftime("%Y-%m-%d"), WEEKDAY_CN[last.weekday()],
            len(days)))
        if not args.no_days:
            cells = ["%s(%s)" % (x.strftime("%m-%d"), WEEKDAY_CN[x.weekday()][1])
                     for x in days]
            for i in range(0, len(cells), 4):
                print("    " + "  ".join(cells[i:i + 4]))
        cursor = last + timedelta(days=1)
    print("共 %d 个 Sprint，合计 %d 个工作日（周末%s，节假日排除 %d 天）。" % (
        args.sprints, total,
        "不计" if skip_weekend else "计入",
        len(holidays)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
