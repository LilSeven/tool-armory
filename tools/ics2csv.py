#!/usr/bin/env python3
"""日历导出 CSV (ics2csv) —— 解析 iCalendar (.ics) 文件中的 VEVENT，
提取摘要与起止时间，导出为 CSV 日程表。

只用 Python 标准库。支持：
  - 展开折叠行（RFC 5545 以空格/制表符开头的续行）
  - DTSTART/DTEND 带时区 (TZID=...)、UTC (Z 后缀)、纯日期 (VALUE=DATE)
  - 同时解析 VEVENT 的 SUMMARY / LOCATION / DESCRIPTION（若有）

用法:
    python ics2csv.py 输入.ics 输出.csv
示例:
    python ics2csv.py calendar.ics schedule.csv
"""

import csv
import re
import sys
from datetime import datetime, date

PROP_RE = re.compile(
    r'^(?P<name>[A-Za-z0-9-]+(?:;[^:]*)?)?:(?P<value>.*)$'
)


def unfold_lines(text):
    """展开 RFC 5545 折叠行：CRLF 后跟空格/Tab 的行拼接回一行。"""
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def parse_prop(line):
    """把一行属性解析为 (名称, 参数dict, 值)。"""
    head, _, value = line.partition(":")
    parts = head.split(";")
    name = parts[0].upper()
    params = {}
    for p in parts[1:]:
        k, _, v = p.partition("=")
        params[k.upper()] = v.strip('"')
    return name, params, value


def parse_ical_dt(value, params):
    """解析 iCalendar 日期时间值，返回可读字符串。"""
    value = value.strip()
    fmt_out = "%Y-%m-%d %H:%M"
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value[:8], "%Y%m%d").strftime("%Y-%m-%d")
    tz = params.get("TZID")
    m = re.fullmatch(r"(\d{8})T(\d{6})(Z?)", value)
    if not m:
        return value  # 无法识别时原样保留
    d, t, zulu = m.groups()
    dt = datetime.strptime(d + t, "%Y%m%d%H%M%S")
    suffix = " UTC" if zulu else (f" ({tz})" if tz else "")
    return dt.strftime(fmt_out) + suffix


def extract_events(text):
    """遍历展开后的行，收集 VEVENT 的关键字段。"""
    events = []
    cur = None
    for line in unfold_lines(text):
        line = line.rstrip("\n")
        if not line.strip():
            continue
        upper = line.upper()
        if upper.startswith("BEGIN:VEVENT"):
            cur = {}
            continue
        if upper.startswith("END:VEVENT"):
            if cur is not None:
                events.append(cur)
            cur = None
            continue
        if cur is None or ":" not in line:
            continue
        name, params, value = parse_prop(line)
        if name == "DTSTART":
            cur["start"] = parse_ical_dt(value, params)
        elif name == "DTEND":
            cur["end"] = parse_ical_dt(value, params)
        elif name in ("SUMMARY", "LOCATION", "DESCRIPTION"):
            cur[name.lower()] = unescape_text(value)
    return events


def unescape_text(value):
    """还原 RFC 5545 TEXT 转义。"""
    value = value.replace("\\n", " ").replace("\\N", " ")
    value = value.replace("\\,", ",").replace("\\;", ";")
    value = value.replace("\\\\", "\\")
    return value


def main(argv):
    if len(argv) != 3:
        print(__doc__.strip())
        return 2
    src, dst = argv[1], argv[2]
    with open(src, "r", encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    events = extract_events(text)
    fields = ["summary", "start", "end", "location", "description"]
    with open(dst, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["摘要", "开始时间", "结束时间", "地点", "描述"])
        for ev in events:
            writer.writerow([ev.get(k, "") for k in fields])
    print(f"导出 {len(events)} 个事件 -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
