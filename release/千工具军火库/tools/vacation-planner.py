#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""请假方案优化（vacation-planner）——结合节假日表推荐请哪几天假能拼出最长连续假期。

用途：
    给定年份、法定放假日表（--holidays）与调休补班表（--workdays），枚举
    “连续请假 1..N 天”的所有方案，计算每种方案能拼出的最长连休区间
    （自动把前后相邻的周末/节假日并入），按连休天数与“连休/请假”性价比
    排序输出 Top N，并给出“最长连休 / 最佳性价比”两个摘要。

示例：
    python vacation-planner.py --year 2026 --holidays 2026-10-01..2026-10-07 --workdays 2026-09-27
    python vacation-planner.py --year 2026 --holidays 2026-01-01,2026-05-01..2026-05-05 --max-leave 2 --top 5
    python vacation-planner.py --year 2027

退出码：0 成功；2 参数错误。
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
        if not part:
            continue
        if ".." in part:
            a, b = part.split("..", 1)
            d1, d2 = _date(a.strip()), _date(b.strip())
            if d2 < d1:
                raise argparse.ArgumentTypeError("日期区间倒序：%s" % part)
            while d1 <= d2:
                out.append(d1)
                d1 += dt.timedelta(days=1)
        else:
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


def fmt_block(block):
    if len(block) == 1:
        return block[0].isoformat()
    return "%s~%s" % (block[0].isoformat(), block[-1].isoformat())


def find_plans(year, holidays, makeups, max_leave):
    """返回 [{span, ratio, block, start, end}, ...]，按连休天数与性价比排序。"""

    def is_off(d):
        return d in holidays or (d.weekday() >= 5 and d not in makeups)

    first, last = dt.date(year, 1, 1), dt.date(year, 12, 31)
    cands = []
    d = first
    while d <= last:
        if not is_off(d):
            cands.append(d)
        d += dt.timedelta(days=1)

    plans = []
    run = []
    for d in cands + [None]:
        if d is not None and (not run or (d - run[-1]).days == 1):
            run.append(d)
            continue
        length = len(run)
        for i in range(length):
            for j in range(i, min(length, i + max_leave)):
                block = run[i:j + 1]
                s, e = block[0], block[-1]
                guard = 0
                while is_off(s - dt.timedelta(days=1)) and guard < 400:
                    s -= dt.timedelta(days=1)
                    guard += 1
                guard = 0
                while is_off(e + dt.timedelta(days=1)) and guard < 400:
                    e += dt.timedelta(days=1)
                    guard += 1
                span = (e - s).days + 1
                plans.append({"span": span, "ratio": span / len(block),
                              "block": block, "start": s, "end": e})
        run = [d] if d is not None else []
    plans.sort(key=lambda x: (-x["span"], -x["ratio"], x["start"]))
    return plans


def main(argv=None):
    _utf8_stdio()
    p = argparse.ArgumentParser(
        description="结合节假日表推荐请哪几天假能拼出最长连续假期")
    p.add_argument("--year", type=int, default=dt.date.today().year,
                   help="年份（默认当年）")
    p.add_argument("--holidays", type=_date_list, default=[],
                   help="法定放假日，逗号分隔，支持 a..b 区间")
    p.add_argument("--workdays", type=_date_list, default=[],
                   help="调休补班日（周末上班），逗号分隔")
    p.add_argument("--max-leave", type=int, default=3,
                   help="最多连续请假天数（默认 3）")
    p.add_argument("--top", type=int, default=10, help="输出前 N 个方案（默认 10）")
    args = p.parse_args(argv)

    if args.max_leave < 1 or args.top < 1:
        print("错误：--max-leave 与 --top 必须 >= 1", file=sys.stderr)
        return 2
    if not 1 <= args.year <= 9999:
        print("错误：年份超出范围", file=sys.stderr)
        return 2

    holidays = set(args.holidays)
    makeups = set(args.workdays)
    plans = find_plans(args.year, holidays, makeups, args.max_leave)

    print("请假方案推荐 · %d 年 · 最多连请 %d 天 · 放假 %d 天 / 补班 %d 天" %
          (args.year, args.max_leave, len(holidays), len(makeups)))
    if not holidays:
        print("提示：未提供 --holidays，仅按双休拼假；提供法定节假日表结果更准")
    if not plans:
        print("该年没有可安排请假的工作日")
        return 0
    print("-" * 74)
    print(lj("排名", 8) + lj("请假日期", 28) + lj("连休区间", 28) +
          rj("连休", 8) + rj("效率", 8))
    for i, pl in enumerate(plans[:args.top], 1):
        b = pl["block"]
        lv = b[0].strftime("%m-%d") if len(b) == 1 else \
            "%s~%s" % (b[0].strftime("%m-%d"), b[-1].strftime("%m-%d"))
        sv = "%s~%s" % (pl["start"].strftime("%m-%d"), pl["end"].strftime("%m-%d"))
        print(lj(str(i), 8) + lj(lv, 28) + lj(sv, 28) +
              rj("%d天" % pl["span"], 8) + rj("%.1f" % pl["ratio"], 8))
    print("-" * 74)
    best = plans[0]
    print("最长连休：请假 %d 天（%s）→ %s ~ %s 连休 %d 天（效率 %.1f）" %
          (len(best["block"]), fmt_block(best["block"]),
           best["start"].isoformat(), best["end"].isoformat(),
           best["span"], best["ratio"]))
    cheap = max(plans, key=lambda x: (x["ratio"], x["span"],
                                      -x["start"].toordinal()))
    print("最佳性价比：请假 %d 天（%s）→ 连休 %d 天（效率 %.1f）" %
          (len(cheap["block"]), fmt_block(cheap["block"]),
           cheap["span"], cheap["ratio"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
