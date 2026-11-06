#!/usr/bin/env python3
"""夏令时判断器 —— 判断某日期某时区是否处于夏令时，并列出该年 DST 进入/退出日期。

用法:
    python dst-check.py America/New_York 2026-07-01
    python dst-check.py America/New_York 2026-01-01
    python dst-check.py Asia/Shanghai 2026-07-01       # 无 DST 的时区
    python dst-check.py --year 2026 America/New_York   # 只列全年切换日期

说明: 逐日扫描该年偏移变化定位切换日，再用二分法精确到分钟。
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


def offset_at(tz, moment_utc):
    local = moment_utc.astimezone(tz)
    return local.utcoffset(), local.tzname()


def transitions_in_year(tz, year):
    """返回该年的切换列表 [(utc时刻, 新偏移, 新缩写, 是否进入DST), ...]，按时间排序。"""
    start = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
    end = dt.datetime(year + 1, 1, 1, tzinfo=dt.timezone.utc)
    result = []
    t = start
    prev_off, prev_abbr = offset_at(tz, t)
    one_day = dt.timedelta(days=1)
    while t < end:
        nxt = min(t + one_day, end)
        off, abbr = offset_at(tz, nxt)
        if off != prev_off:
            lo, hi = t, nxt
            while (hi - lo) > dt.timedelta(minutes=1):
                mid = lo + (hi - lo) / 2
                off_mid, _ = offset_at(tz, mid)
                if off_mid == prev_off:
                    lo = mid
                else:
                    hi = mid
            result.append((hi, off, abbr, off > prev_off))
            prev_off, prev_abbr = off, abbr
        t = nxt
    return result


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="判断指定日期是否夏令时，并列出该年 DST 进入/退出日期")
    p.add_argument("zone", help="IANA 时区名，如 Asia/Shanghai、America/New_York")
    p.add_argument("date", nargs="?", metavar="YYYY-MM-DD",
                   help="要判断的日期 (默认今天)")
    p.add_argument("--year", type=int, metavar="YYYY",
                   help="只列出指定年份的切换日期，不做单日判断")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    tz = load_zone(args.zone)

    if args.year:
        year = args.year
        query_date = None
    elif args.date:
        try:
            query_date = dt.date.fromisoformat(args.date)
        except ValueError:
            raise SystemExit(f"错误: 日期格式应为 YYYY-MM-DD，收到 {args.date!r}")
        year = query_date.year
    else:
        query_date = dt.date.today()
        year = query_date.year

    if not query_date:
        pass
    else:
        noon_utc = dt.datetime(query_date.year, query_date.month, query_date.day,
                               12, 0, tzinfo=dt.timezone.utc)
        offset, abbr = offset_at(tz, noon_utc)
        # 用当地正午复核 DST 状态（避免 UTC 正午跨日误差）
        local_noon = dt.datetime(query_date.year, query_date.month, query_date.day,
                                 12, 0, tzinfo=tz)
        is_dst = bool(local_noon.dst() and local_noon.dst() != dt.timedelta(0))
        print(f"日期 {query_date} 在 {args.zone}: "
              f"{'处于夏令时 (DST)' if is_dst else '不处于夏令时'}  "
              f"UTC{fmt_offset(offset)} ({abbr})")

    print(f"\n{year} 年 {args.zone} 的 DST 切换:")
    trans = transitions_in_year(tz, year)
    if not trans:
        print("  (该年无偏移切换，即不实行夏令时)")
    for moment, off, abbr, entering in trans:
        kind = "进入 DST" if entering else "退出 DST"
        # 换算到当地时间展示
        local = moment.astimezone(tz)
        print(f"  {kind}: 当地 {local:%Y-%m-%d %H:%M}  "
              f"(UTC {moment:%Y-%m-%d %H:%M})  -> UTC{fmt_offset(off)} ({abbr})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
