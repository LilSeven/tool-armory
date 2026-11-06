#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务工期拆分（deadline-split）——按每日工作日配额把总工作量拆分到具体工作日，输出进度计划。

用途：
    给定总工作量与每日配额，从开始日期起逐个工作日分配任务量，自动跳过
    周末（可用 --no-skip-weekends 关闭）与指定节假日，输出逐日计划表
    （当日量 / 累计量 / 进度条），以及预计完成日期、所需工作日数等汇总。

示例：
    python deadline-split.py --total 40 --quota 8 --start 2026-11-02
    python deadline-split.py --total 100 --quota 6 --start 2026-11-02 --holidays 2026-11-05,2026-11-06
    python deadline-split.py --total 21 --quota 3.5 --start 2026-11-02 --no-skip-weekends --unit 点

退出码：0 成功；2 参数或输入错误。
"""

import argparse
import datetime as dt
import sys

WEEK_CN = "一二三四五六日"


def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _date(s):
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError("无效日期 %r，应为 YYYY-MM-DD" % s)


def _date_list(s):
    out = []
    for part in s.split(","):
        part = part.strip()
        if part:
            out.append(_date(part))
    if not out:
        raise argparse.ArgumentTypeError("日期列表不能为空")
    return out


def disp_len(s):
    return sum(2 if ord(ch) > 127 else 1 for ch in s)


def lj(s, w):
    return s + " " * max(w - disp_len(s), 0)


def rj(s, w):
    return " " * max(w - disp_len(s), 0) + s


def _num(x):
    return "%g" % x


def build_plan(total, quota, start, skip_weekends, holidays, cap=3660):
    """逐工作日分配，返回 [(日期, 当日量, 累计量), ...] 与剩余量。"""
    rows = []
    remaining = float(total)
    done = 0.0
    d = start
    for _ in range(cap):
        if remaining <= 1e-9:
            break
        if (d.weekday() < 5 or not skip_weekends) and d not in holidays:
            amount = min(quota, remaining)
            remaining -= amount
            done += amount
            rows.append((d, amount, done))
        d += dt.timedelta(days=1)
    return rows, remaining


def main(argv=None):
    _utf8_stdio()
    p = argparse.ArgumentParser(
        description="按每日工作日配额把总工作量拆分到具体工作日，输出进度计划")
    p.add_argument("--total", type=float, required=True, help="总工作量（>0）")
    p.add_argument("--quota", type=float, required=True,
                   help="每个工作日可完成的量（>0）")
    p.add_argument("--start", type=_date, required=True, help="开始日期 YYYY-MM-DD")
    p.add_argument("--holidays", type=_date_list, default=[],
                   help="额外跳过的节假日，逗号分隔，如 2026-11-05,2026-11-06")
    p.add_argument("--no-skip-weekends", action="store_true",
                   help="周末也照常安排（默认跳过周六、周日）")
    p.add_argument("--unit", default="h", help="工作量单位名称（默认 h）")
    args = p.parse_args(argv)

    if args.total <= 0 or args.quota <= 0:
        print("错误：--total 与 --quota 必须为正数", file=sys.stderr)
        return 2

    skip_weekends = not args.no_skip_weekends
    holidays = set(args.holidays)
    rows, remaining = build_plan(args.total, args.quota, args.start,
                                 skip_weekends, holidays)
    if remaining > 1e-9:
        print("错误：3660 天推算范围内无法完成，请检查 --total 与 --quota",
              file=sys.stderr)
        return 2

    finish = rows[-1][0]
    print("任务工期拆分 · 总量 %s %s · 每日配额 %s %s" %
          (_num(args.total), args.unit, _num(args.quota), args.unit))
    print("开始 %s（周%s） · 跳过周末：%s · 额外节假日：%d 天" %
          (args.start.isoformat(), WEEK_CN[args.start.weekday()],
           "是" if skip_weekends else "否", len(holidays)))
    print("-" * 64)
    print(lj("日期", 12) + lj("星期", 6) + rj("当日", 8) + rj("累计", 10) + "  进度")
    bar_w = 20
    for d, amount, cum in rows:
        pct = cum / args.total
        bar = ("#" * int(round(pct * bar_w))).ljust(bar_w, "-")
        print(lj(d.isoformat(), 12) + lj("周" + WEEK_CN[d.weekday()], 6) +
              rj(_num(amount), 8) + rj(_num(cum), 10) +
              "  %s %5.1f%%" % (bar, pct * 100))
    print("-" * 64)
    print("预计完成：%s（周%s） · 共 %d 个工作日 · 收尾日安排 %s %s" %
          (finish.isoformat(), WEEK_CN[finish.weekday()], len(rows),
           _num(rows[-1][1]), args.unit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
