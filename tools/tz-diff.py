#!/usr/bin/env python3
"""两地时差计算 —— 计算两个时区在指定日期的时差，自动考虑各自的夏令时差异。

用法:
    python tz-diff.py Asia/Shanghai America/New_York             # 当前时刻时差
    python tz-diff.py Asia/Shanghai America/New_York 2026-07-01  # 指定日期
    python tz-diff.py Europe/London America/New_York 2026-07-01 15:30

说明: 以指定日期（默认今天）当地时间 12:00（或 --time 指定时间）为准，
分别取两地当时的 UTC 偏移再求差。若该日恰逢切换且时间影响结果，可指定 --time。
Windows 上无系统时区库时会自动回退到 Git 自带的 zoneinfo 数据库。
仅使用 Python 标准库。
"""

import argparse
import datetime as dt
import os
import sys
import zoneinfo

_FALLBACK_TZPATHS = [
    r"C:\Program Files\Git\mingw64\share\zoneinfo",
    r"C:\Program Files (x86)\Git\mingw64\share\zoneinfo",
    "/usr/share/zoneinfo",
]


def load_zone(name):
    try:
        return zoneinfo.ZoneInfo(name)
    except zoneinfo.ZoneInfoNotFoundError:
        for path in _FALLBACK_TZPATHS:
            if os.path.exists(os.path.join(path, *name.split("/"))):
                zoneinfo.reset_tzpath([path])
                return zoneinfo.ZoneInfo(name)
        raise SystemExit(f"错误: 找不到时区 {name!r}，请使用 IANA 名称如 Asia/Shanghai")


def fmt_offset(td):
    total = int(td.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{sign}{total // 3600:02d}:{total // 60 % 60:02d}"


def fmt_delta(td):
    """把时差格式化为 'X 小时 Y 分钟'（带符号）。"""
    total = int(td.total_seconds())
    sign = "-" if total < 0 else "+"
    total = abs(total)
    h, rem = divmod(total, 3600)
    m = rem // 60
    return f"{sign}{h} 小时 {m:02d} 分钟"


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="计算两个 IANA 时区在指定日期的时差（考虑各自 DST）")
    p.add_argument("zone_a", help="第一个时区，如 Asia/Shanghai")
    p.add_argument("zone_b", help="第二个时区，如 America/New_York")
    p.add_argument("date", nargs="?", metavar="YYYY-MM-DD",
                   help="指定日期 (默认今天)")
    p.add_argument("--time", metavar="HH:MM", default="12:00",
                   help="取当地几点来判断偏移 (默认 12:00)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    tz_a = load_zone(args.zone_a)
    tz_b = load_zone(args.zone_b)

    if args.date:
        try:
            day = dt.date.fromisoformat(args.date)
        except ValueError:
            raise SystemExit(f"错误: 日期格式应为 YYYY-MM-DD，收到 {args.date!r}")
    else:
        day = dt.date.today()
    try:
        hh, mm = (int(x) for x in args.time.split(":", 1))
        clock = dt.time(hh, mm)
    except (ValueError, TypeError):
        raise SystemExit(f"错误: 时间格式应为 HH:MM，收到 {args.time!r}")

    local_a = dt.datetime.combine(day, clock, tzinfo=tz_a)
    same_moment = local_a.astimezone(dt.timezone.utc)  # 同一瞬间

    off_a = local_a.utcoffset()
    local_b = same_moment.astimezone(tz_b)
    off_b = local_b.utcoffset()
    diff = off_a - off_b

    dst_a = bool(local_a.dst() and local_a.dst() != dt.timedelta(0))
    dst_b = bool(local_b.dst() and local_b.dst() != dt.timedelta(0))

    print(f"日期: {day}  当地 {clock}（以 {args.zone_a} 计）")
    print(f"  {args.zone_a}: {local_a:%Y-%m-%d %H:%M}  UTC{fmt_offset(off_a)}"
          f"  ({local_a.tzname()}，{'夏令时' if dst_a else '标准时间'})")
    print(f"  {args.zone_b}: {local_b:%Y-%m-%d %H:%M}  UTC{fmt_offset(off_b)}"
          f"  ({local_b.tzname()}，{'夏令时' if dst_b else '标准时间'})")
    if dst_a != dst_b:
        who = args.zone_a if dst_a else args.zone_b
        print(f"  注意: 两地夏令时状态不同，{who} 正实行夏令时")
    print(f"  时差: {args.zone_a} 比 {args.zone_b} {fmt_delta(diff)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
