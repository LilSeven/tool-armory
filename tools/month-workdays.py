#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""月度工作日统计 —— 统计某年 1-12 月各月的工作日天数，并给出每月最后
一个工作日，生成结账/排产日历参考表；可选导出 CSV（utf-8-sig，Excel 友好）。

口径:
    工作日 = 非周末且非节假日的日子 + 周末补班日；
    同一日期既是节假日又是补班日时，按补班（上班）处理；
    “节假”列统计当月全部节假日日期（含落在周末的，不影响工作日口径）。

用法:
    python month-workdays.py 2027
    python month-workdays.py 2027 --holiday 01-01,02-15..02-17,10-01..10-07 --workday 02-20,02-27
    python month-workdays.py 2027 --holiday 2027-01-01..2027-01-03 --csv out.csv

日期格式:
    --holiday / --workday 可重复或逗号分隔，每项为 MM-DD（按统计年份解释）、
    YYYY-MM-DD 或 A..B 区间（含两端）；不属于统计年份的日期被忽略并提示。
    省略年份参数时默认统计当前年份。

示例输出:
    $ python month-workdays.py 2027
    2027 年月度工作日统计（未配置节假日/补班）
    月份  天数  周末  节假  补班  工作日  月末工作日
    01月    31    10     0     0      21  2027-01-29
    ...
    合计   365   104     0     0     261  2027-12-31

退出码: 0 成功; 2 参数或日期格式错误。
仅用 Python 标准库，单文件。
"""

from __future__ import annotations

import argparse
import calendar
import csv
import sys
from datetime import date, timedelta


def _setup_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def expand_dates(specs, year) -> set:
    """把 MM-DD / YYYY-MM-DD / A..B（可逗号分隔）展开成 date 集合。"""
    def one(t: str) -> date:
        parts = t.strip().split("-")
        if len(parts) == 2:
            try:
                return date(year, int(parts[0]), int(parts[1]))
            except ValueError:
                raise ValueError(f"无效日期: {t}") from None
        try:
            return date.fromisoformat(t.strip())
        except ValueError:
            raise ValueError(f"无效日期: {t}") from None

    out = set()
    for item in specs:
        for piece in str(item).split(","):
            piece = piece.strip()
            if not piece:
                continue
            if ".." in piece:
                a, _, b = piece.partition("..")
                d1, d2 = one(a), one(b)
                if d2 < d1:
                    raise ValueError(f"日期区间倒序: {piece}")
                if (d2 - d1).days > 400:
                    raise ValueError(f"日期区间过长(>400 天): {piece}")
                cur = d1
                while cur <= d2:
                    out.add(cur)
                    cur += timedelta(days=1)
            else:
                out.add(one(piece))
    return out


def clip_to_year(dates: set, year: int, label: str) -> set:
    extra = sorted(d for d in dates if d.year != year)
    if extra:
        print(f"注意: 忽略不属于 {year} 年的{label}: "
              + "，".join(d.isoformat() for d in extra), file=sys.stderr)
    return {d for d in dates if d.year == year}


def month_rows(year: int, holidays: set, workdays: set):
    """返回 12 行 [月份, 总天数, 周末, 节假, 补班, 工作日, 月末工作日] 与合计。"""
    rows = []
    tot = [0] * 5
    for m in range(1, 13):
        ndays = calendar.monthrange(year, m)[1]
        wend = hol = wb = wd = 0
        last_wd = None
        for dd in range(1, ndays + 1):
            d = date(year, m, dd)
            is_weekend = d.weekday() >= 5
            is_wb = d in workdays
            is_hol = d in holidays and not is_wb  # 补班优先
            if is_weekend:
                wend += 1
            if d in holidays:
                hol += 1
            if is_wb:
                wb += 1
            if is_wb or (not is_weekend and not is_hol):
                wd += 1
                last_wd = d
        rows.append([f"{m:02d}", ndays, wend, hol, wb, wd,
                     last_wd.isoformat() if last_wd else "-"])
        for i in range(5):
            tot[i] += rows[-1][i + 1]
    return rows, tot


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="统计某年各月的工作日天数，生成结账日历参考表")
    parser.add_argument("year", nargs="?", type=int,
                        help="统计年份（缺省为当前年份）")
    parser.add_argument("--holiday", action="append", default=[], metavar="D",
                        help="节假日日期 MM-DD / YYYY-MM-DD / A..B，可重复或逗号分隔")
    parser.add_argument("--workday", action="append", default=[], metavar="D",
                        help="补班日（周末调休上班）日期，格式同 --holiday")
    parser.add_argument("--csv", metavar="FILE", help="把表格导出为 CSV 文件")
    args = parser.parse_args(argv)

    year = args.year if args.year is not None else date.today().year
    try:
        holidays = clip_to_year(expand_dates(args.holiday, year), year, "节假日")
        workdays = clip_to_year(expand_dates(args.workday, year), year, "补班日")
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    rows, tot = month_rows(year, holidays, workdays)
    print(f"{year} 年月度工作日统计"
          f"（节假日 {len(holidays)} 天 / 补班 {len(workdays)} 天；"
          f"工作日 = 非周末且非节假日 + 补班）")
    print("月份  天数  周末  节假  补班  工作日  月末工作日")
    for r in rows:
        print(f"{r[0]}月  {r[1]:>4}  {r[2]:>4}  {r[3]:>4}  {r[4]:>4}  {r[5]:>6}  {r[6]}")
    year_last = rows[-1][6]
    print(f"合计  {tot[0]:>4}  {tot[1]:>4}  {tot[2]:>4}  {tot[3]:>4}  {tot[4]:>6}  {year_last}")

    if args.csv:
        try:
            with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["月份", "总天数", "周末天数", "节假日天数",
                            "补班天数", "工作日天数", "月末工作日"])
                for r in rows:
                    w.writerow(r)
                w.writerow(["合计", tot[0], tot[1], tot[2], tot[3], tot[4], year_last])
        except OSError as exc:
            print(f"错误: 无法写入 {args.csv}: {exc}", file=sys.stderr)
            return 2
        print(f"已导出 CSV -> {args.csv}")
    return 0


if __name__ == "__main__":
    _setup_stdio()
    sys.exit(main())
