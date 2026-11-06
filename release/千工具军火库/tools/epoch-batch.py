#!/usr/bin/env python3
"""文本时间戳批量替换 (epoch-batch)

用正则扫描文件或管道文本，把所有 Unix 时间戳（秒/毫秒/微秒/纳秒级，自动识别量级）
原地替换为本地可读时间。支持 --utc、--fmt 自定义格式、--inplace 写回文件。

注意: 10 位纯数字（如某些 ID）与秒级时间戳无法区分，会被一并转换；
      9 位以下 / 11-12 位 / 14-15 位等非 10/13/16/19 位长度的数字不会匹配。

用法:
  python epoch-batch.py access.log                     # 读文件，替换后输出到 stdout
  python epoch-batch.py access.log -i                  # 原地写回（保留 .bak 备份）
  cat notes.txt | python epoch-batch.py -              # 从管道读取
  python epoch-batch.py log.txt --fmt "%Y/%m/%d %H:%M" --utc
"""

import argparse
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone

_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=timezone.utc)

# 10 位=秒，13 位=毫秒，16 位=微秒，19 位=纳秒（3 位一组的小数部分）；避免匹配纯年份/电话号码等短数字
TS_RE = re.compile(r"(?<![\d.])((?:1[0-9]|2[0-2])\d{8})(\d{3}){0,3}(?![\d.])")

DIVISORS = {10: 1, 13: 1000, 16: 10 ** 6, 19: 10 ** 9}


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


def looks_like_ts(total_digits):
    """按位数判断是否是合理的时间戳量级: 10/13/16/19 位。"""
    return total_digits in DIVISORS


def replace_match(m, tz, fmt):
    digits = m.group(1) + (m.group(2) or "")
    if not looks_like_ts(len(digits)):
        return m.group(0)
    ts = int(digits)
    unit = DIVISORS[len(digits)]
    secs, frac = divmod(ts, unit)
    try:
        dt = _EPOCH_UTC + timedelta(seconds=secs)
        dt = dt.astimezone(tz) if tz is not None else dt.astimezone()
    except (OverflowError, OSError, ValueError):
        return m.group(0)
    out = dt.strftime(fmt)
    if unit > 1:
        ms = round(frac / unit * 1000)
        out += ".%03d" % ms
    return out


def process_text(text, tz, fmt):
    return TS_RE.sub(lambda m: replace_match(m, tz, fmt), text)


def main():
    ap = argparse.ArgumentParser(description="把文本中的 Unix 时间戳替换为可读时间")
    ap.add_argument("file", nargs="?", help="输入文件；'-' 或省略表示 stdin")
    ap.add_argument("-i", "--inplace", action="store_true", help="原地写回文件（自动留 .bak 备份）")
    ap.add_argument("--utc", action="store_true", help="用 UTC 而非本地时区显示")
    ap.add_argument("--tz", default=None, help="指定 IANA 时区（如 Asia/Shanghai），优先于 --utc")
    ap.add_argument("--fmt", default="%Y-%m-%d %H:%M:%S", help="strftime 输出格式，缺省 %%Y-%%m-%%d %%H:%%M:%%S")
    ap.add_argument("--no-backup", action="store_true", help="原地写回时不留 .bak")
    args = ap.parse_args()

    if args.tz:
        try:
            tz = get_zone(args.tz)
        except ValueError as e:
            print("错误: %s" % e, file=sys.stderr)
            return 1
    elif args.utc:
        tz = timezone.utc
    else:
        tz = None  # 本地时区

    source = args.file or "-"
    if source == "-":
        if args.inplace:
            print("错误: --inplace 不能用于 stdin 输入", file=sys.stderr)
            return 1
        text = sys.stdin.read()
        sys.stdout.write(process_text(text, tz, args.fmt))
        return 0

    try:
        with open(source, "r", encoding="utf-8", errors="replace", newline="") as f:
            text = f.read()
    except OSError as e:
        print("错误: 读取 %s 失败: %s" % (source, e), file=sys.stderr)
        return 1

    out = process_text(text, tz, args.fmt)
    n = len(TS_RE.findall(text)) - sum(
        1 for m in TS_RE.finditer(text) if not looks_like_ts(len(m.group(1) + (m.group(2) or "")))
    )
    if args.inplace:
        if not args.no_backup:
            shutil.copy2(source, source + ".bak")
        tmp = source + ".tmp-epoch-batch"
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(out)
        os.replace(tmp, source)
        print("已替换 %d 处时间戳 -> %s（备份: %s）" % (n, source, "" if args.no_backup else source + ".bak"),
              file=sys.stderr)
    else:
        sys.stdout.write(out)
        print("共替换 %d 处时间戳" % n, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
