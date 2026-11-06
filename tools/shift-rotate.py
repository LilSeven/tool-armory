#!/usr/bin/env python3
"""轮班表生成（shift-rotate）

用途：
    按人数与周期生成 N 人轮换排班表：每人在岗 --cycle 天后换给下一位，
    依此循环，支持自定义起始日期、排班天数与成员姓名，并自动统计
    每人值班天数、标注每次换班日。

参数：
    -n/--people  参与轮换的人数（默认 4）
    -c/--cycle   每人在岗的连续天数（默认 1）
    -s/--start   起始日期 YYYY-MM-DD（默认今天）
    -d/--days    生成排班表的总天数（默认 14）
    --names      逗号分隔的成员姓名（数量须 >= 人数，缺省用 成员1..N）

示例命令：
    python shift-rotate.py -n 4 -c 2 -s 2026-11-02 -d 12 --names 张三,李四,王五,赵六
    python shift-rotate.py --people 3 --start 2026-11-02 --days 7
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


def main(argv=None):
    _setup_stdout()
    parser = argparse.ArgumentParser(
        description="按人数与周期生成 N 人轮换排班表",
        epilog="示例: python shift-rotate.py -n 4 -c 2 -s 2026-11-02 -d 12 --names 张三,李四,王五,赵六",
    )
    parser.add_argument("-n", "--people", type=int, default=4, help="参与轮换的人数（默认 4）")
    parser.add_argument("-c", "--cycle", type=int, default=1, help="每人在岗的连续天数（默认 1）")
    parser.add_argument("-s", "--start", help="起始日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("-d", "--days", type=int, default=14, help="排班表总天数（默认 14）")
    parser.add_argument("--names", help="逗号分隔的成员姓名，数量须 >= 人数")
    args = parser.parse_args(argv)

    if args.people < 1:
        parser.error("--people 至少为 1")
    if args.cycle < 1:
        parser.error("--cycle 至少为 1")
    if args.days < 1:
        parser.error("--days 至少为 1")
    try:
        start = (datetime.strptime(args.start, "%Y-%m-%d").date()
                 if args.start else date.today())
    except ValueError:
        parser.error("--start 日期格式应为 YYYY-MM-DD")

    if args.names:
        names = [x.strip() for x in args.names.split(",") if x.strip()]
        if len(names) < args.people:
            parser.error("--names 提供了 %d 个名字，少于人数 %d" % (len(names), args.people))
        if len(names) > args.people:
            print("提示: 名字多于人数，仅使用前 %d 个。" % args.people, file=sys.stderr)
            names = names[:args.people]
    else:
        names = ["成员%d" % i for i in range(1, args.people + 1)]

    period = args.people * args.cycle
    print("轮班表: %d 人 x 每岗 %d 天，周期 %d 天一轮；共 %d 天" % (
        args.people, args.cycle, period, args.days))
    print("起始日: %s（%s）" % (start.strftime("%Y-%m-%d"), WEEKDAY_CN[start.weekday()]))
    print()
    print("日期          星期   值班     备注")
    print("-" * 44)
    counts = {n: 0 for n in names}
    for i in range(args.days):
        d = start + timedelta(days=i)
        who = names[(i // args.cycle) % args.people]
        counts[who] += 1
        note = "开始" if i == 0 else ("换班" if i % args.cycle == 0 else "")
        print("%s   %s   %s     %s" % (
            d.strftime("%Y-%m-%d"), WEEKDAY_CN[d.weekday()], who.ljust(4), note))
    print("-" * 44)
    print("值班天数: " + "、".join("%s %d 天" % (n, c) for n, c in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
