#!/usr/bin/env python3
"""跨国会议对照表（meeting-planner）

用途：
    给定一个 UTC 时刻，为分布在不同城市的参会者计算各自的本地时间，
    并按本地小时给出"适宜度"评级，生成一张对照表，帮助挑选对所有人
    都尽量友好的跨国会议时间。

适宜度规则（按参会者本地小时划分）：
    08:00-11:59 或 14:00-17:59                ★★★  适宜
    07:00-07:59 / 12:00-13:59 / 18:00-20:59   ★★   一般
    21:00-22:59                               ★    勉强
    23:00-06:59                               ✗    深夜/清晨，不宜

时区说明：
    优先使用系统 tz 数据库（zoneinfo，自动处理夏令时）；若系统缺少
    tz 数据（常见于未安装 tzdata 的 Windows），则回退为内置的标准时
    固定偏移，并在输出中提示"未考虑夏令时"。

示例命令：
    python meeting-planner.py 2026-11-05T14:00
    python meeting-planner.py "2026-11-05 14:00" --cities 北京,伦敦,纽约,东京
    python meeting-planner.py --list-cities
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

# (城市名, IANA 时区名, 无 tz 数据时使用的标准时 UTC 偏移/分钟)
CITIES = [
    ("北京",   "Asia/Shanghai",       8 * 60),
    ("香港",   "Asia/Hong_Kong",      8 * 60),
    ("台北",   "Asia/Taipei",         8 * 60),
    ("新加坡", "Asia/Singapore",      8 * 60),
    ("东京",   "Asia/Tokyo",          9 * 60),
    ("首尔",   "Asia/Seoul",          9 * 60),
    ("新德里", "Asia/Kolkata",        5 * 60 + 30),
    ("迪拜",   "Asia/Dubai",          4 * 60),
    ("莫斯科", "Europe/Moscow",       3 * 60),
    ("悉尼",   "Australia/Sydney",    10 * 60),
    ("伦敦",   "Europe/London",       0),
    ("巴黎",   "Europe/Paris",        60),
    ("柏林",   "Europe/Berlin",       60),
    ("纽约",   "America/New_York",    -5 * 60),
    ("多伦多", "America/Toronto",     -5 * 60),
    ("芝加哥", "America/Chicago",     -6 * 60),
    ("旧金山", "America/Los_Angeles", -8 * 60),
    ("圣保罗", "America/Sao_Paulo",   -3 * 60),
]
CITY_INDEX = {name: (iana, off) for name, iana, off in CITIES}

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _setup_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def load_zone(iana, fallback_minutes):
    """返回 (tzinfo, 是否来自 tz 数据库)。"""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(iana), True
    except Exception:
        return timezone(timedelta(minutes=fallback_minutes)), False


def rate(hour):
    """按本地小时返回 (星级 0-3, 说明文字)。"""
    if 8 <= hour <= 11 or 14 <= hour <= 17:
        return 3, "适宜"
    if hour == 7 or 12 <= hour <= 13 or 18 <= hour <= 20:
        return 2, "一般"
    if 21 <= hour <= 22:
        return 1, "勉强"
    return 0, "深夜/清晨，不宜"


def stars(level):
    return "★" * level if level > 0 else "✗"


def parse_utc(text):
    text = text.strip()
    if text.endswith("Z"):
        text = text[:-1]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    raise ValueError("无法识别的时间格式: %r，示例: 2026-11-05T14:00" % text)


def main(argv=None):
    _setup_stdout()
    parser = argparse.ArgumentParser(
        description="给定 UTC 时刻，生成多城市参会者本地时间与适宜度对照表",
        epilog="示例: python meeting-planner.py 2026-11-05T14:00 --cities 北京,伦敦,纽约",
    )
    parser.add_argument("utc_time", nargs="?",
                        help='UTC 时刻，如 2026-11-05T14:00 或 "2026-11-05 14:00"')
    parser.add_argument("--cities", default="北京,伦敦,纽约,东京",
                        help="逗号分隔的城市名（用 --list-cities 查看全部）")
    parser.add_argument("--list-cities", action="store_true",
                        help="列出支持的城市后退出")
    args = parser.parse_args(argv)

    if args.list_cities:
        print("支持的城市（括号内为无 tz 数据时使用的标准时偏移）:")
        for name, iana, off in CITIES:
            sign = "+" if off >= 0 else "-"
            minutes = abs(off)
            print("  %s（UTC%s%02d:%02d，%s）" % (
                name.ljust(4), sign, minutes // 60, minutes % 60, iana))
        return 0

    if not args.utc_time:
        parser.error("缺少 utc_time 参数（或使用 --list-cities）")
    try:
        utc_dt = parse_utc(args.utc_time)
    except ValueError as exc:
        parser.error(str(exc))

    wanted = [c.strip() for c in args.cities.split(",") if c.strip()]
    unknown = [c for c in wanted if c not in CITY_INDEX]
    if unknown:
        parser.error("不支持的城市: %s（用 --list-cities 查看全部）" % ", ".join(unknown))
    if not wanted:
        parser.error("--cities 至少需要一个城市")

    rows = []
    tz_from_db = True
    for name in wanted:
        iana, off = CITY_INDEX[name]
        tz, from_db = load_zone(iana, off)
        tz_from_db = tz_from_db and from_db
        local = utc_dt.astimezone(tz)
        level, text = rate(local.hour)
        rows.append((name, local, level, text))

    print("UTC 时刻: %s（%s）" % (
        utc_dt.strftime("%Y-%m-%d %H:%M"), WEEKDAY_CN[utc_dt.weekday()]))
    if not tz_from_db:
        print("提示: 系统缺少 tz 数据库，以下时间按标准时固定偏移计算（未考虑夏令时）。")
    print()
    print("城市      本地时间             星期  适宜度")
    print("-" * 50)
    for name, local, level, text in rows:
        mark = stars(level)
        print("%s     %s   %s   %s  %s" % (
            name.ljust(4),
            local.strftime("%Y-%m-%d %H:%M"),
            WEEKDAY_CN[local.weekday()],
            mark.ljust(3),
            text))
    print("-" * 50)
    best = max(level for _, _, level, _ in rows)
    if best == 0:
        print("结论: 该时刻对所有列出城市都不适宜，建议换时间。")
    else:
        ok_names = [name for name, _, level, _ in rows if level == best]
        print("结论: 该时刻对 %s 较为友好（%s）。" % ("、".join(ok_names), stars(best)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
