#!/usr/bin/env python3
"""多时区时间换算 (tz-convert)

给定一个时刻（Unix 时间戳或日期字符串），同时列出若干 IANA 时区中的对应本地时间对照表。

用法:
  python tz-convert.py 1700000000                       # 按时间戳查询
  python tz-convert.py "2023-11-14 22:13:20" --from-tz Asia/Shanghai
  python tz-convert.py now --zones UTC,Asia/Shanghai,America/New_York
  python tz-convert.py 1700000000 --zones UTC,Europe/London,Asia/Tokyo --fmt "%H:%M (%Z)"
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    HAVE_ZI = True
except ImportError:  # pragma: no cover
    HAVE_ZI = False

DEFAULT_ZONES = "UTC,Asia/Shanghai,Asia/Tokyo,Europe/London,America/New_York,America/Los_Angeles"


# ------------ 标准库回退：常用时区表（本机缺 IANA tzdata 数据时使用） ------------
import calendar as _cal
import re as _re
from datetime import timedelta as _td, tzinfo as _tzinfo, timezone as _utc, datetime as _dt

_FALLBACK_ZONES = {
    # 名称: (标准偏移秒, DST 增量秒, DST 规则 us/eu/au/nz)
    "UTC": (0, 0, None), "GMT": (0, 0, None), "Etc/UTC": (0, 0, None),
    "Asia/Shanghai": (28800, 0, None), "Asia/Chongqing": (28800, 0, None),
    "Asia/Hong_Kong": (28800, 0, None), "Asia/Taipei": (28800, 0, None),
    "Asia/Singapore": (28800, 0, None), "Asia/Manila": (28800, 0, None),
    "Asia/Kuala_Lumpur": (28800, 0, None), "Asia/Macau": (28800, 0, None),
    "Asia/Tokyo": (32400, 0, None), "Asia/Seoul": (32400, 0, None),
    "Asia/Bangkok": (25200, 0, None), "Asia/Jakarta": (25200, 0, None),
    "Asia/Ho_Chi_Minh": (25200, 0, None), "Asia/Kolkata": (19800, 0, None),
    "Asia/Colombo": (19800, 0, None), "Asia/Karachi": (18000, 0, None),
    "Asia/Dubai": (14400, 0, None),
    "Europe/London": (0, 3600, "eu"), "Europe/Dublin": (0, 3600, "eu"),
    "Europe/Paris": (3600, 3600, "eu"), "Europe/Berlin": (3600, 3600, "eu"),
    "Europe/Madrid": (3600, 3600, "eu"), "Europe/Rome": (3600, 3600, "eu"),
    "Europe/Amsterdam": (3600, 3600, "eu"), "Europe/Vienna": (3600, 3600, "eu"),
    "Europe/Stockholm": (3600, 3600, "eu"), "Europe/Warsaw": (3600, 3600, "eu"),
    "Europe/Brussels": (3600, 3600, "eu"), "Europe/Zurich": (3600, 3600, "eu"),
    "Europe/Athens": (7200, 3600, "eu"), "Europe/Helsinki": (7200, 3600, "eu"),
    "Europe/Kyiv": (7200, 3600, "eu"), "Europe/Bucharest": (7200, 3600, "eu"),
    "Europe/Moscow": (10800, 0, None),
    "America/New_York": (-18000, 3600, "us"), "America/Toronto": (-18000, 3600, "us"),
    "America/Detroit": (-18000, 3600, "us"),
    "America/Chicago": (-21600, 3600, "us"), "America/Winnipeg": (-21600, 3600, "us"),
    "America/Mexico_City": (-21600, 0, None),
    "America/Denver": (-25200, 3600, "us"), "America/Edmonton": (-25200, 3600, "us"),
    "America/Phoenix": (-25200, 0, None),
    "America/Los_Angeles": (-28800, 3600, "us"), "America/Vancouver": (-28800, 3600, "us"),
    "America/Anchorage": (-32400, 3600, "us"),
    "America/Sao_Paulo": (-10800, 0, None),
    "America/Argentina/Buenos_Aires": (-10800, 0, None),
    "America/Bogota": (-18000, 0, None), "America/Lima": (-18000, 0, None),
    "Australia/Sydney": (36000, 3600, "au"), "Australia/Melbourne": (36000, 3600, "au"),
    "Australia/Canberra": (36000, 3600, "au"), "Australia/Hobart": (36000, 3600, "au"),
    "Australia/Adelaide": (34200, 3600, "au"),
    "Australia/Brisbane": (36000, 0, None), "Australia/Perth": (28800, 0, None),
    "Pacific/Auckland": (43200, 3600, "nz"), "Pacific/Fiji": (43200, 0, None),
}


class _FallbackZone(_tzinfo):
    """简化 tzinfo：固定标准偏移 + 现代 DST 规则（US 2007 起 / EU 1996 起 / 澳 / 新西兰）。"""

    def __init__(self, name, std, dst_delta, rule):
        self._zname, self._std, self._dst_delta, self._rule = name, std, dst_delta, rule

    @staticmethod
    def _sunday(y, m, n):
        first_sun = 1 + (6 - _dt(y, m, 1).weekday()) % 7
        if n > 0:
            day = first_sun + 7 * (n - 1)
        else:
            last = _cal.monthrange(y, m)[1]
            day = last - (last - first_sun) % 7
        return _dt(y, m, day)

    def _bounds_utc(self, y):
        std, dd, rule = self._std, self._dst_delta, self._rule
        if rule == "us":    # 3 月第 2 个周日 02:00 本地标准时间起，11 月第 1 个周日止
            return (self._sunday(y, 3, 2) + _td(hours=2) - _td(seconds=std),
                    self._sunday(y, 11, 1) + _td(hours=2) - _td(seconds=std + dd))
        if rule == "eu":    # 3 月最后一个周日 01:00 UTC 起，10 月最后一个周日止
            return (self._sunday(y, 3, -1) + _td(hours=1),
                    self._sunday(y, 10, -1) + _td(hours=1))
        if rule == "au":    # 10 月第 1 个周日 02:00 起，4 月第 1 个周日 03:00 止（南半球跨年）
            return (self._sunday(y, 10, 1) + _td(hours=2) - _td(seconds=std),
                    self._sunday(y, 4, 1) + _td(hours=3) - _td(seconds=std + dd))
        if rule == "nz":
            return (self._sunday(y, 9, -1) + _td(hours=2) - _td(seconds=std),
                    self._sunday(y, 4, 1) + _td(hours=3) - _td(seconds=std + dd))
        return None, None

    def _is_dst(self, utc_naive):
        if not self._rule:
            return False
        s, e = self._bounds_utc(utc_naive.year)
        if self._rule in ("au", "nz"):
            return utc_naive >= s or utc_naive < e
        return s <= utc_naive < e

    def _active(self, dt):
        if dt is None or self._rule is None:
            return False
        utc_guess = (dt.replace(tzinfo=_utc.utc) - _td(seconds=self._std)).replace(tzinfo=None)
        return self._is_dst(utc_guess)

    def utcoffset(self, dt):
        return _td(seconds=self._std + (self._dst_delta if self._active(dt) else 0))

    def dst(self, dt):
        return _td(seconds=self._dst_delta if self._active(dt) else 0)

    def tzname(self, dt):
        return self._zname + ("(DST)" if self._active(dt) else "")

    def __repr__(self):
        return self._zname


def get_zone(name):
    """解析时区：ZoneInfo 优先，缺 tzdata 时用内置回退表；支持 'UTC+8' 形式；LOCAL/空 返回 None。"""
    if name is None:
        return None
    name = name.strip()
    if not name or name.upper() == "LOCAL":
        return None
    m = _re.fullmatch(r"UTC([+-])(\d{1,2})(?::(\d{2}))?", name, _re.I)
    if m:
        sec = int(m.group(2)) * 3600 + int(m.group(3) or 0) * 60
        return _utc(_td(seconds=sec if m.group(1) == "+" else -sec))
    try:
        return ZoneInfo(name)
    except Exception:
        pass
    z = _FALLBACK_ZONES.get(name)
    if z is not None:
        return _FallbackZone(name, *z)
    sample = ", ".join(sorted(_FALLBACK_ZONES)[:6]) + " ..."
    raise ValueError("未知时区 %r（本机无 IANA tzdata 数据；可用内置时区如 %s，或用 UTC+8 形式）"
                     % (name, sample))


def parse_input(s):
    s = s.strip()
    if s.lower() == "now":
        return datetime.now(timezone.utc), True
    if s.lstrip("+-").isdigit():
        v = int(s)
        a = abs(v)
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        if a >= 10 ** 15:
            return epoch + timedelta(milliseconds=v), True
        if a >= 10 ** 12:
            return epoch + timedelta(milliseconds=v), True
        # epoch+timedelta 而非 fromtimestamp：Windows 下负时间戳会抛 OSError
        return epoch + timedelta(seconds=v), True
    s2 = s.replace("T", " ")
    if s2.endswith("Z"):
        s2 = s2[:-1] + "+00:00"
    fmts = ["%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"]
    for f in fmts:
        try:
            return datetime.strptime(s2, f), False  # naive
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s), False
    except ValueError:
        raise ValueError("无法识别的时刻: %s" % s)


def main():
    ap = argparse.ArgumentParser(description="列出给定时刻在各 IANA 时区的本地时间对照表")
    ap.add_argument("moment", nargs="?", default="now", help="Unix 时间戳、日期字符串或 now")
    ap.add_argument("--from-tz", default=None, help="输入日期字符串所属时区（缺省本地时区）")
    ap.add_argument("--zones", default=DEFAULT_ZONES, help="逗号分隔的 IANA 时区列表")
    ap.add_argument("--fmt", default="%Y-%m-%d %H:%M:%S", help="strftime 格式")
    ap.add_argument("--sort", choices=["zone", "offset"], default="zone", help="按名称或 UTC 偏移排序")
    args = ap.parse_args()

    if not HAVE_ZI:
        print("错误: 当前 Python 缺少 zoneinfo 模块（需 3.9+）", file=sys.stderr)
        return 1

    try:
        dt, was_ts = parse_input(args.moment)
    except ValueError as e:
        print("错误: %s" % e, file=sys.stderr)
        return 1
    except (OverflowError, OSError) as e:
        print("错误: 时间超出可表示范围: %s" % e, file=sys.stderr)
        return 1

    if dt.tzinfo is None:
        if args.from_tz:
            try:
                dt = dt.replace(tzinfo=get_zone(args.from_tz))
            except ValueError as e:
                print("错误: %s" % e, file=sys.stderr)
                return 1
        elif not was_ts:
            dt = dt.astimezone()

    zones = [z.strip() for z in args.zones.split(",") if z.strip()]
    rows = []
    for z in zones:
        try:
            tz = get_zone(z)
            loc = dt.astimezone(tz)
        except Exception as e:
            rows.append((z, None, "错误: %s" % e, 0))
            continue
        off = loc.utcoffset() or timedelta(0)
        rows.append((z, loc, loc.strftime(args.fmt) + " " + (loc.tzname() or ""), off.total_seconds()))
    if args.sort == "offset":
        rows.sort(key=lambda r: r[3])

    print("给定时刻（UTC）: %s" % dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    print("Unix 秒        : %d" % int(dt.timestamp()))
    print("-" * 58)
    w = max(len(r[0]) for r in rows) + 2
    for z, loc, text, _ in rows:
        if loc is None:
            print("  %s%s" % (z.ljust(w), text))
        else:
            off = loc.strftime("%z")
            off_fmt = "UTC%+03d:%02d" % (int(off[1:3]) * (1 if off[0] == "+" else -1), int(off[3:5]))
            print("  %s%s  %s" % (z.ljust(w), text, off_fmt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
