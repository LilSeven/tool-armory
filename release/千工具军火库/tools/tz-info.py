#!/usr/bin/env python3
"""时区信息查询 —— 用 zoneinfo 查询指定时区的 UTC 偏移、缩写与未来切换时间点。

用法:
    python tz-info.py Asia/Shanghai                 # 当前时刻的信息
    python tz-info.py America/New_York              # 含未来 DST 切换点
    python tz-info.py America/New_York --count 4    # 列出未来 4 次切换
    python tz-info.py America/New_York --at 2026-07-01T12:00  # 指定时刻查询

说明: 切换时间点通过对 UTC 偏移做逐步加倍+二分搜索求得。
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


def _utc(td_or_dt):
    if isinstance(td_or_dt, dt.datetime):
        return td_or_dt
    return dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc) + td_or_dt


def offset_at(tz, moment_utc):
    """给定 UTC 时刻，返回该时区当时的标准/DST 偏移与缩写。"""
    local = moment_utc.astimezone(tz)
    return local.utcoffset(), local.tzname(), local.dst()


def next_transition(tz, after_utc, max_years=3):
    """搜索 after_utc 之后下一次 utcoffset 发生变化的 UTC 时刻；无则返回 None。"""
    horizon = after_utc + dt.timedelta(days=365 * max_years)
    step = dt.timedelta(days=30)
    t = after_utc
    off0, _, _ = offset_at(tz, t)
    while t < horizon:
        t2 = min(t + step, horizon)
        off1, _, _ = offset_at(tz, t2)
        if off1 != off0:
            # 二分缩小到 [t, t2]，直到区间足够小 (切换在整点/半点附近)
            lo, hi = t, t2
            while (hi - lo) > dt.timedelta(minutes=1):
                mid = lo + (hi - lo) / 2
                off_mid, _, _ = offset_at(tz, mid)
                if off_mid == off0:
                    lo = mid
                else:
                    hi = mid
            return hi
        t = t2
        # 逐步加长步长，加快远离切换点的搜索
        if step < dt.timedelta(days=180):
            step = dt.timedelta(days=step.days * 2)
    return None


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="查询 IANA 时区的 UTC 偏移、缩写与未来切换时间点")
    p.add_argument("zone", help="IANA 时区名，如 Asia/Shanghai、America/New_York")
    p.add_argument("--at", metavar="ISO_DATETIME",
                   help="查询指定时刻 (如 2026-07-01T12:00)，默认当前时刻")
    p.add_argument("--count", type=int, default=3, metavar="N",
                   help="列出未来 N 次切换 (默认 3)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    tz = load_zone(args.zone)

    if args.at:
        naive = dt.datetime.fromisoformat(args.at)
        moment = naive.replace(tzinfo=dt.timezone.utc)  # 按 UTC 解释查询时刻
    else:
        moment = dt.datetime.now(dt.timezone.utc)

    offset, abbr, dst = offset_at(tz, moment)
    local = moment.astimezone(tz)
    print(f"时区:      {args.zone}  ({tz.key if hasattr(tz, 'key') else args.zone})")
    print(f"查询时刻:  UTC {moment:%Y-%m-%d %H:%M}  当地 {local:%Y-%m-%d %H:%M}")
    print(f"UTC 偏移:  {fmt_offset(offset)}")
    print(f"缩写:      {abbr}")
    print(f"夏令时:    {'是，+1h' if dst and dst != dt.timedelta(0) else '否'}")

    print(f"\n未来 {args.count} 次偏移切换 (UTC 时间):")
    t = moment
    found = 0
    for _ in range(args.count):
        nxt = next_transition(tz, t)
        if nxt is None:
            if found == 0:
                print("  (未来的切换点不在数据库范围内)")
            break
        new_off, new_abbr, _ = offset_at(tz, nxt)
        delta = (new_off - offset_at(tz, t)[0]).total_seconds() / 3600
        print(f"  {nxt:%Y-%m-%d %H:%M} UTC  -> {new_abbr}  "
              f"UTC{fmt_offset(new_off)}  ({'+' if delta > 0 else ''}{delta:g}h)")
        t = nxt
        found += 1
    if found == 0:
        print("  (该时区无 DST 切换或未找到)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
