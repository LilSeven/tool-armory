#!/usr/bin/env python3
"""HTTP 日期（RFC 7231）解析与生成。

在 RFC 7231 HTTP 日期与 ISO 8601 / 常见 datetime 写法之间互转：
    - 生成 IMF-fixdate：Sun, 06 Nov 1994 08:49:37 GMT（用于 Date、
      If-Modified-Since、Expires 等头，可用 --header 直接拼出头格式）。
    - 解析 IMF-fixdate 及两种过时格式（RFC 850: Sunday, 06-Nov-94 08:49:37
      GMT；asctime: Sun Nov  6 08:49:37 1994），输出 ISO 8601（UTC）。
方向自动判断：以星期名开头按 HTTP 日期解析，否则按 datetime 解析生成
HTTP 日期；也可用 --to-http / --from-http 强制指定方向。

仅用 Python 标准库，单文件。

示例命令：
    python -I http-date.py --now
    python -I http-date.py "Sun, 06 Nov 1994 08:49:37 GMT"
    python -I http-date.py "2026-11-02 12:00:00" --header If-Modified-Since
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import re
import sys

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

ISO_INPUT_FORMATS = [
    "%Y-%m-%dT%H:%M:%S%z",   # 2026-11-02T12:00:00+0800 / ...Z（py3.7+ 支持 Z? 用 %z 兼容 +HH:MM/+HHMM）
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
]


def parse_http(value: str) -> dt.datetime:
    """解析 RFC 7231 三种格式，返回 naive-UTC datetime。失败抛 ValueError。"""
    v = value.strip()
    # IMF-fixdate: Sun, 06 Nov 1994 08:49:37 GMT
    m = re.fullmatch(
        r"([A-Z][a-z]{2}), (\d{2}) ([A-Z][a-z]{2}) (\d{4}) "
        r"(\d{2}):(\d{2}):(\d{2}) GMT", v)
    if m:
        return _from_parts(int(m.group(4)), m.group(3), int(m.group(2)),
                           int(m.group(5)), int(m.group(6)), int(m.group(7)),
                           m.group(1))
    # RFC 850 (过时): Sunday, 06-Nov-94 08:49:37 GMT（两位年份按 RFC 7231 规则外推）
    m = re.fullmatch(
        r"([A-Z][a-z]{2,8}day|[A-Z][a-z]{2,8}), (\d{2})-([A-Z][a-z]{2})-(\d{2}) "
        r"(\d{2}):(\d{2}):(\d{2}) GMT", v)
    if m:
        yy = int(m.group(4))
        year = yy + (1900 if yy >= 50 else 2000)
        return _from_parts(year, m.group(3), int(m.group(2)),
                           int(m.group(5)), int(m.group(6)), int(m.group(7)),
                           m.group(1))
    # asctime (过时): Sun Nov  6 08:49:37 1994
    m = re.fullmatch(
        r"([A-Z][a-z]{2}) ([A-Z][a-z]{2}) ( ?\d{1,2}) (\d{2}):(\d{2}):(\d{2}) (\d{4})", v)
    if m:
        return _from_parts(int(m.group(7)), m.group(2), int(m.group(3)),
                           int(m.group(4)), int(m.group(5)), int(m.group(6)),
                           m.group(1))
    raise ValueError(f"不是合法的 HTTP 日期: {value!r}")


def _from_parts(year: int, mon_s: str, day: int, hh: int, mm: int, ss: int,
                wday_s: str) -> dt.datetime:
    months = {m: i + 1 for i, m in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"))}
    if mon_s not in months:
        raise ValueError(f"未知月份缩写 {mon_s!r}")
    d = dt.date(year, months[mon_s], day)  # 月份/日期非法会在这里抛 ValueError
    if not wday_s.startswith(WEEKDAYS[d.weekday()]):
        raise ValueError(f"星期名 {wday_s!r} 与日期 {d} 不符")
    t = dt.time(hh, mm, ss)  # 时分秒超界会抛 ValueError
    return dt.datetime.combine(d, t)


def to_http(moment: dt.datetime) -> str:
    """生成 IMF-fixdate（总是 UTC / GMT）。naive 视为 UTC，aware 转换到 UTC。"""
    if moment.tzinfo is not None:
        moment = moment.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return email.utils.formatdate(
        moment.replace(tzinfo=dt.timezone.utc).timestamp(), usegmt=True)


def parse_datetime(value: str) -> dt.datetime:
    v = value.strip().replace("Z", "+0000") if value.strip().endswith("Z") else value.strip()
    for fmt in ISO_INPUT_FORMATS:
        try:
            return dt.datetime.strptime(v, fmt)
        except ValueError:
            continue
    # 兜底：fromisoformat（支持微秒等）
    return dt.datetime.fromisoformat(value.strip())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RFC 7231 HTTP 日期与 datetime 互转")
    ap.add_argument("value", nargs="?", help="HTTP 日期或 datetime 字符串；省略则用当前时间")
    ap.add_argument("--to-http", action="store_true", help="强制按 datetime->HTTP 方向转换")
    ap.add_argument("--from-http", action="store_true", help="强制按 HTTP->datetime 方向转换")
    ap.add_argument("--header", metavar="NAME", help="额外按 'NAME: <HTTP日期>' 头格式输出")
    ap.add_argument("--now", action="store_true", help="输出当前时刻的 HTTP 日期")
    ns = ap.parse_args(argv)

    if ns.now or (ns.value is None and not ns.from_http):
        moment = dt.datetime.now(dt.timezone.utc)
        http = to_http(moment)
        print(http)
        print("ISO 8601 (UTC):", moment.strftime("%Y-%m-%dT%H:%M:%SZ"))
        if ns.header:
            print(f"{ns.header}: {http}")
        return 0
    if ns.value is None:
        ap.error("需要提供一个日期值，或使用 --now")

    value = ns.value.strip()
    looks_http = (bool(re.match(r"^[A-Z][a-z]{2}([a-z]*),", value))
                  or bool(re.match(r"^[A-Z][a-z]{2} [A-Z][a-z]{2}\s", value))
                  or "GMT" in value)
    try:
        if ns.from_http or (looks_http and not ns.to_http):
            udt = parse_http(value)
            print("HTTP 日期 :", value)
            print("ISO 8601 (UTC):", udt.strftime("%Y-%m-%dT%H:%M:%SZ"))
            print("Unix 秒   :", int(udt.replace(tzinfo=dt.timezone.utc).timestamp()))
        else:
            moment = parse_datetime(value)
            http = to_http(moment)
            print("输入      :", value)
            print("HTTP 日期 :", http)
            if ns.header:
                print(f"{ns.header}: {http}")
        return 0
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
