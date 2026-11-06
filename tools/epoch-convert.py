#!/usr/bin/env python3
"""Unix 时间戳互转 (epoch-convert)

秒/毫秒/微秒级 Unix 时间戳与可读日期双向换算，支持指定 IANA 时区。
自动识别输入的量级（10 位=秒、13 位=毫秒、16 位=微秒、19 位=纳秒），也可用 --unit 强制指定。

用法:
  python epoch-convert.py 1700000000                 # 时间戳 -> 可读时间
  python epoch-convert.py 1700000000123              # 毫秒级时间戳
  python epoch-convert.py "2023-11-14 22:13:20" --tz Asia/Shanghai   # 日期 -> 时间戳
  python epoch-convert.py 1700000000 --unit s --tz UTC
  python epoch-convert.py --now                     # 当前时间的时间戳
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    HAVE_ZI = True
except ImportError:  # pragma: no cover
    HAVE_ZI = False

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


def auto_unit(v):
    a = abs(v)
    if a >= 10 ** 18:
        return "ns"
    if a >= 10 ** 15:
        return "us"
    if a >= 10 ** 12:
        return "ms"
    return "s"


DIVISOR = {"s": 1, "ms": 10 ** 3, "us": 10 ** 6, "ns": 10 ** 9}


def ts_to_datetime(ts, unit):
    secs, frac = divmod(ts, DIVISOR[unit])
    # 用 epoch+timedelta 而非 fromtimestamp：Windows 下负时间戳（1970 前）fromtimestamp 会抛 OSError
    dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=secs)
    frac_s = frac / DIVISOR[unit]
    return dt, frac_s


def fmt(dt, frac_s, tz, with_frac):
    if tz is not None:
        dt = dt.astimezone(tz)
    else:
        dt = dt.astimezone()
    base = dt.strftime("%Y-%m-%d %H:%M:%S")
    if with_frac and frac_s:
        micro = round(frac_s * 1_000_000)
        if micro:
            base += (".%06d" % micro).rstrip("0")
    off = dt.strftime("%z")
    off_fmt = "UTC%+03d:%02d" % (int(off[1:3]) * (1 if off[0] == "+" else -1), int(off[3:5])) if off else "UTC"
    name = dt.tzname() or ""
    return "%s %s (%s %s)" % (base, name, off_fmt, dt.tzinfo)


def parse_datetime(s):
    s = s.strip()
    s = s.replace("T", " ")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    fmts = ["%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
            "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"]
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        raise ValueError("无法识别的日期格式: %s" % s)


def main():
    ap = argparse.ArgumentParser(description="Unix 时间戳与可读日期双向换算")
    ap.add_argument("value", nargs="?", help="时间戳数字或日期字符串")
    ap.add_argument("--unit", choices=["s", "ms", "us", "ns"], help="强制指定时间戳单位（缺省自动识别）")
    ap.add_argument("--tz", default=None, help="IANA 时区，如 Asia/Shanghai、UTC（缺省本地时区）")
    ap.add_argument("--now", action="store_true", help="显示当前时间戳（正反两个方向）")
    args = ap.parse_args()

    if args.now:
        now = datetime.now(timezone.utc)
        print("当前 UTC 时间 : %s" % now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
        print("当前本地时间  : %s" % now.astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])
        print("Unix 秒       : %d" % int(now.timestamp()))
        print("Unix 毫秒     : %d" % int(now.timestamp() * 1000))
        return 0

    if not args.value:
        ap.error("需要提供一个 value，或使用 --now")

    raw = args.value.strip()
    try:
        tz = get_zone(args.tz)
    except ValueError as e:
        print("错误: %s" % e, file=sys.stderr)
        return 1

    # 纯数字 -> 时间戳
    if raw.lstrip("+-").isdigit():
        v = int(raw)
        unit = args.unit or auto_unit(v)
        dt, frac = ts_to_datetime(v, unit)
        print("输入     : %d （识别为 %s 级）" % (v, unit))
        print("UTC      : %s" % fmt(dt, frac, timezone.utc, True))
        print("目标时区 : %s" % fmt(dt, frac, tz, True))
        return 0

    # 否则当日期解析
    try:
        dt = parse_datetime(raw)
    except ValueError as e:
        print("错误: %s" % e, file=sys.stderr)
        return 1
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz) if tz is not None else dt.astimezone()
    ts_s = dt.timestamp()
    print("输入     : %s" % dt.isoformat())
    print("Unix 秒  : %d" % int(ts_s))
    print("Unix 毫秒: %d" % round(ts_s * 1000))
    print("Unix 微秒: %d" % round(ts_s * 1_000_000))
    print("UTC      : %s" % dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
