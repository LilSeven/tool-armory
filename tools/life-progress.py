#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""人生进度可视化：按出生日期与预期寿命，把已度过的时间渲染成格子进度图。

默认以“周”为单位（每年按 52 周计，每行 52 格约等于一年），
也可用 --unit months/days 按月/天渲染。只用 Python 标准库。

用法:
    python life-progress.py --birth 1990-06-15
    python life-progress.py --birth 1990-06-15 --life 90 --unit months
    python life-progress.py --birth 1990-06-15 --unit days --width 60
    python life-progress.py --birth 1990-06-15 --ascii

参数:
    --birth YYYY-MM-DD   出生日期（必填，不能晚于今天）
    --life N             预期寿命（岁），默认 80，范围 1~150
    --unit NAME          单位: weeks(默认) / months / days
    --width N            每行格数，默认 weeks=52 / months=12 / days=52
    --ascii              用 # 和 . 代替 █ 和 ░（兼容老终端）
"""

import argparse
import datetime as dt
import sys

UNITS = {
    "weeks": {"label": "周", "per_year": 52.0, "width": 52},
    "months": {"label": "月", "per_year": 12.0, "width": 12},
    "days": {"label": "天", "per_year": 365.25, "width": 52},
}


def _setup_streams():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", newline="")
        except Exception:
            pass


def fail(msg):
    print("错误: %s" % msg, file=sys.stderr)
    raise SystemExit(1)


def parse_birth(text):
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        fail("出生日期格式应为 YYYY-MM-DD，收到 %r" % text)


def add_years(d, n):
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # 2 月 29 日遇上平年，按 2/28 算
        return d.replace(year=d.year + n, day=28)


def count_units(unit, birth, today, life):
    """返回 (总格数, 已度过格数)。"""
    if unit == "weeks":
        total = life * 52
        lived = (today - birth).days // 7
    elif unit == "months":
        total = life * 12
        lived = (today.year - birth.year) * 12 + (today.month - birth.month)
        if today.day < birth.day:  # 当月尚未过完，不计入
            lived -= 1
    else:  # days
        total = (add_years(birth, life) - birth).days
        lived = (today - birth).days
    return total, max(0, min(lived, total))


def render(unit, total, lived, width, filled, empty):
    per_year = UNITS[unit]["per_year"]
    lines = []
    for start in range(0, total, width):
        age = int(start / per_year)  # 行首标注该行起始时的大致年龄
        cells = "".join(filled if i < lived else empty
                        for i in range(start, min(start + width, total)))
        lines.append("%4d | %s" % (age, cells))
    return lines


def main(argv=None):
    _setup_streams()

    parser = argparse.ArgumentParser(
        prog="life-progress",
        description="按出生日期与预期寿命渲染人生进度格子图。")
    parser.add_argument("--birth", required=True, help="出生日期，格式 YYYY-MM-DD")
    parser.add_argument("--life", type=int, default=80, help="预期寿命(岁)，默认 80")
    parser.add_argument("--unit", choices=sorted(UNITS), default="weeks",
                        help="时间单位，默认 weeks")
    parser.add_argument("--width", type=int, default=None, help="每行格数")
    parser.add_argument("--ascii", action="store_true", help="纯 ASCII 字符输出")
    args = parser.parse_args(argv)

    birth = parse_birth(args.birth)
    today = dt.date.today()
    if birth > today:
        fail("出生日期 %s 不能晚于今天 %s" % (birth, today))
    if not 1 <= args.life <= 150:
        fail("--life 应在 1~150 之间，收到 %d" % args.life)
    width = args.width if args.width is not None else UNITS[args.unit]["width"]
    if not 4 <= width <= 200:
        fail("--width 应在 4~200 之间，收到 %d" % width)

    total, lived = count_units(args.unit, birth, today, args.life)
    pct = lived * 100.0 / total if total else 100.0
    filled, empty = ("#", ".") if args.ascii else ("█", "░")
    label = UNITS[args.unit]["label"]
    days = (today - birth).days

    print("出生 %s | 今天 %s | 已活 %d 天" % (birth, today, days))
    print("单位: %s | 已度过 %d/%d %s | %.1f%%" % (label, lived, total, label, pct))
    done = int(round(pct / 100 * 20))
    print("[%s%s] %.1f%%" % (filled * done, empty * (20 - done), pct))
    print()
    for line in render(args.unit, total, lived, width, filled, empty):
        print(line)
    print()
    remaining = total - lived
    print("剩余约 %d %s ≈ %.1f 年（按预期寿命 %d 岁计）"
          % (remaining, label, remaining / UNITS[args.unit]["per_year"], args.life))
    return 0


if __name__ == "__main__":
    sys.exit(main())
