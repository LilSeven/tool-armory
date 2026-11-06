#!/usr/bin/env python3
"""多城市世界时钟 —— 持续刷新显示多个城市当前时间、UTC 偏移与是否夏令时。

用法:
    python world-clock.py                                    # 默认城市循环刷新
    python world-clock.py Asia/Shanghai America/New_York     # 指定时区
    python world-clock.py 北京=Asia/Shanghai 纽约=America/New_York  # 自定义标签=时区
    python world-clock.py --once                             # 只刷新一次后退出
    python world-clock.py --interval 5                       # 每 5 秒刷新

说明: Windows 上无系统时区库时会自动回退到 Git 自带的 zoneinfo 数据库。
仅使用 Python 标准库 (zoneinfo / argparse / time 等)。
"""

import argparse
import datetime as dt
import os
import sys
import time
import zoneinfo

# 常用默认城市
DEFAULT_CITIES = ["Asia/Shanghai", "Asia/Tokyo", "Europe/London",
                  "America/New_York", "UTC"]

# Windows 下 zoneinfo 需要 tzdata 包；若缺失则回退到 Git 自带的时区数据库
_FALLBACK_TZPATHS = [
    r"C:\Program Files\Git\mingw64\share\zoneinfo",
    r"C:\Program Files (x86)\Git\mingw64\share\zoneinfo",
    "/usr/share/zoneinfo",
]


def load_zone(name):
    """按 IANA 名称加载时区；必要时回退到 Git 的 zoneinfo 数据库。"""
    try:
        return zoneinfo.ZoneInfo(name)
    except zoneinfo.ZoneInfoNotFoundError:
        for path in _FALLBACK_TZPATHS:
            if os.path.exists(os.path.join(path, *name.split("/"))):
                zoneinfo.reset_tzpath([path])
                return zoneinfo.ZoneInfo(name)
        raise SystemExit(f"错误: 找不到时区 {name!r}，请使用 IANA 名称如 Asia/Shanghai")


def fmt_offset(td):
    """把 timedelta 偏移格式化为 +08:00 形式。"""
    total = int(td.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{sign}{total // 3600:02d}:{total // 60 % 60:02d}"


def city_line(label, zone, now_utc):
    """返回一个城市的一行显示文本。"""
    local = now_utc.astimezone(zone)
    offset = local.utcoffset()
    dst = local.dst()
    is_dst = bool(dst and dst != dt.timedelta(0))
    return (f"{label:<14} {local:%Y-%m-%d %H:%M:%S}  "
            f"UTC{fmt_offset(offset)}  {'夏令时' if is_dst else '标准时间':<4}"
            f" ({local.tzname()})")


def snapshot(city_pairs):
    now_utc = dt.datetime.now(dt.timezone.utc)
    lines = [f"世界时钟  UTC {now_utc:%Y-%m-%d %H:%M:%S}",
             "-" * 60]
    for label, zone in city_pairs:
        lines.append(city_line(label, zone, now_utc))
    return "\n".join(lines)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="多城市世界时钟：持续刷新显示各城市时间、UTC 偏移与夏令时状态")
    p.add_argument("cities", nargs="*",
                   help="时区列表，可用 标签=时区 格式，如 北京=Asia/Shanghai")
    p.add_argument("--interval", type=float, default=2.0,
                   help="刷新间隔秒数 (默认 2)")
    p.add_argument("--once", action="store_true",
                   help="只显示一次后退出，不循环刷新")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    pairs = []
    for item in (args.cities or DEFAULT_CITIES):
        if "=" in item:
            label, zone_name = item.split("=", 1)
        else:
            label, zone_name = item.split("/")[-1].replace("_", " "), item
        pairs.append((label, load_zone(zone_name)))

    if args.once:
        print(snapshot(pairs))
        return 0

    first = True
    try:
        while True:
            if not first:
                # 简单清屏 (兼容 Windows 终端)
                print("\033[H\033[J", end="")
            print(snapshot(pairs))
            print(f"\n每 {args.interval:g} 秒刷新，Ctrl+C 退出")
            first = False
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n再见。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
