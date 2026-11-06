#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""长周末发现器（long-weekend）——扫描某年找出所有 3 天及以上的连休长周末。

用途：
    给定年份与节假日表（放假日 --holidays + 调休补班日 --workdays），扫描
    全年找出所有长度不小于指定天数（--min-len，默认 3）的连续休息日区间，
    即周末与法定节假日拼成的长周末，标注天数、含法定节假日天数、是否跨年。
    默认只列出包含周六/周日的区间；--all 可同时列出不含周末的连休段。

示例：
    python long-weekend.py --year 2026 --holidays 2026-01-01..2026-01-03,2026-10-01..2026-10-07
    python long-weekend.py --year 2026 --holidays 2026-05-01..2026-05-05 --workdays 2026-04-26 --min-len 4
    python long-weekend.py --year 2027 --all

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


def find_runs(year, holidays, makeups):
    """返回该年（含前后 10 天缓冲）内所有极大连续休息区间 [(起, 止), ...]。"""

    def is_off(d):
        return d in holidays or (d.weekday() >= 5 and d not in makeups)

    scan_from = dt.date(year, 1, 1) - dt.timedelta(days=10)
    scan_to = dt.date(year, 12, 31) + dt.timedelta(days=10)
    runs = []
    start = None
    d = scan_from
    while d <= scan_to:
        if is_off(d):
            if start is None:
                start = d
        elif start is not None:
            runs.append((start, d - dt.timedelta(days=1)))
            start = None
        d += dt.timedelta(days=1)
    if start is not None:
        runs.append((start, scan_to))
    return runs


def main(argv=None):
    _utf8_stdio()
    p = argparse.ArgumentParser(
        description="扫描某年找出所有 N 天及以上的连休长周末")
    p.add_argument("--year", type=int, default=dt.date.today().year,
                   help="年份（默认当年）")
    p.add_argument("--holidays", type=_date_list, default=[],
                   help="放假日表，逗号分隔，支持 a..b 区间")
    p.add_argument("--workdays", type=_date_list, default=[],
                   help="调休补班日（周末上班），逗号分隔")
    p.add_argument("--min-len", type=int, default=3, help="最短连休天数（默认 3）")
    p.add_argument("--all", dest="include_all", action="store_true",
                   help="也列出不含周末的连休段")
    args = p.parse_args(argv)

    if args.min_len < 1:
        print("错误：--min-len 必须 >= 1", file=sys.stderr)
        return 2
    if not 1 <= args.year <= 9999:
        print("错误：年份超出范围", file=sys.stderr)
        return 2

    holidays = set(args.holidays)
    makeups = set(args.workdays)
    y_first, y_last = dt.date(args.year, 1, 1), dt.date(args.year, 12, 31)

    kept, skipped = [], 0
    for s, e in find_runs(args.year, holidays, makeups):
        if e < y_first or s > y_last:
            continue
        if (e - s).days + 1 < args.min_len:
            continue
        days = [s + dt.timedelta(days=i) for i in range((e - s).days + 1)]
        has_weekend = any(d.weekday() >= 5 for d in days)
        if has_weekend or args.include_all:
            kept.append((s, e, days, has_weekend))
        else:
            skipped += 1

    print("%d 年长周末扫描：连休 ≥ %d 天%s · 放假 %d 天 / 补班 %d 天" %
          (args.year, args.min_len,
           "（含全部连休段）" if args.include_all else "（含周末）",
           len(holidays), len(makeups)))
    if not kept:
        print("未发现符合条件的长周末")
    for i, (s, e, days, has_weekend) in enumerate(kept, 1):
        hol = sum(1 for d in days if d in holidays)
        cross = " · 跨年" if (s.year != args.year or e.year != args.year) else ""
        print("%3d) %s（周%s） ~ %s（周%s）  %d 天 | 法定节假日 %d 天 | %s%s" %
              (i, s.isoformat(), WEEK_CN[s.weekday()], e.isoformat(),
               WEEK_CN[e.weekday()], len(days), hol,
               "含周末" if has_weekend else "不含周末", cross))
    if skipped:
        print("另有 %d 个不含周末的连休段未列出（加 --all 查看）" % skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
