#!/usr/bin/env python3
"""三班倒时刻表（shift-grid）

用途：
    生成"早 / 中 / 夜"三班倒的班次时间表：固定的班次时刻、各班组逐日
    （或逐周）轮换安排，以及换班日标注。夜班跨零点，会特别注明
    "次日 08:00 下班"。

班次时刻（固定）：
    早班 08:00 - 16:00
    中班 16:00 - 24:00
    夜班 00:00 - 08:00（跨零点，次日 08:00 下班）

参数：
    --start    起始日期 YYYY-MM-DD（默认今天）
    --days     生成天数（默认 7）
    --groups   恰好 3 个班组名，逗号分隔（默认 甲,乙,丙）
    --mode     day=每日轮换（默认）；week=每 --period 天轮换一次
    --period   week 模式下同一班次连上的天数（默认 7）

示例命令：
    python shift-grid.py --start 2026-11-02 --days 9 --mode week --groups 甲,乙,丙
    python shift-grid.py --start 2026-11-02 --days 7
"""

import argparse
import sys
from datetime import date, datetime, timedelta

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# (班次单字, 时间说明)
SHIFTS = [
    ("早", "08:00-16:00"),
    ("中", "16:00-24:00"),
    ("夜", "00:00-08:00（跨零点，次日 08:00 下班）"),
]


def _setup_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv=None):
    _setup_stdout()
    parser = argparse.ArgumentParser(
        description="生成早/中/夜三班倒的班次时间表与换班日标注",
        epilog="示例: python shift-grid.py --start 2026-11-02 --days 16 --mode week",
    )
    parser.add_argument("--start", help="起始日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--days", type=int, default=7, help="生成天数（默认 7）")
    parser.add_argument("--groups", default="甲,乙,丙",
                        help="恰好 3 个班组名，逗号分隔（默认 甲,乙,丙）")
    parser.add_argument("--mode", choices=("day", "week"), default="day",
                        help="day=每日轮换（默认）；week=每 --period 天轮换一次")
    parser.add_argument("--period", type=int, default=7,
                        help="week 模式下同一班次连上的天数（默认 7）")
    args = parser.parse_args(argv)

    groups = [x.strip() for x in args.groups.split(",") if x.strip()]
    if len(groups) != 3:
        parser.error("三班倒需要恰好 3 个班组，用 --groups 甲,乙,丙 指定")
    if args.days < 1:
        parser.error("--days 至少为 1")
    if args.period < 1:
        parser.error("--period 至少为 1")
    try:
        start = (datetime.strptime(args.start, "%Y-%m-%d").date()
                 if args.start else date.today())
    except ValueError:
        parser.error("--start 日期格式应为 YYYY-MM-DD")

    period = 1 if args.mode == "day" else args.period
    mode_txt = ("每日轮换（每天都是换班日）" if args.mode == "day"
                else "每 %d 天轮换一次" % period)
    print("三班倒时刻表（%s，共 %d 天）" % (mode_txt, args.days))
    print("班次: " + " ｜ ".join("%s班 %s" % (n, t) for n, t in SHIFTS))
    print("轮换顺序: " + "；".join(
        "%s %s" % (groups[g],
                   "→".join("%s班" % SHIFTS[(g + k) % 3][0] for k in range(3)))
        for g in range(3)))
    print()
    print("日期          星期    早班    中班    夜班    备注")
    print("-" * 56)
    for i in range(args.days):
        d = start + timedelta(days=i)
        stint = i // period
        # 班组 g 在第 stint 轮的班次索引 = (g + stint) % 3，
        # 反推各班次列（0早 1中 2夜）应由哪个班组担任。
        cells = [groups[(idx - stint) % 3].ljust(4) for idx in range(3)]
        if args.mode == "day":
            note = "起始" if i == 0 else "换班"
        else:
            note = "起始" if i == 0 else ("换班日" if i % period == 0 else "")
        print("%s   %s   %s  %s" % (
            d.strftime("%Y-%m-%d"),
            WEEKDAY_CN[d.weekday()].ljust(4),
            "   ".join(cells),
            note))
    print("-" * 56)
    print("注: 夜班为 00:00-08:00，跨零点上班、次日 08:00 下班；表中日期为白天早班所在日。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
