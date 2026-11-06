#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日期归一化 (date-normalize)

识别多种常见日期时间格式并统一输出为 ISO 8601 (YYYY-MM-DDTHH:MM:SS)。
支持: 2024/01/05, 5 Jan 2024, Jan 5, 2024, 2024-1-5 3:04 PM, 2024年1月5日,
20240105, ISO 带时区, RFC 风格等。从参数、stdin 或文件逐行处理。

用法:
  python date-normalize.py "2024/01/05"
  python date-normalize.py -f dates.txt        # 逐行归一化文件中的日期
  cat dates.txt | python date-normalize.py     # 从 stdin 逐行读取

示例:
  python date-normalize.py "5 Jan 2024 3:04 PM"   -> 2024-01-05T15:04:00
"""
import argparse
import re
import sys
from datetime import datetime

MONTHS = {m.lower(): i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
FULL_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], 1)}
MONTHS.update(FULL_MONTHS)

FORMATS = [
    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d",
    "%m/%d/%Y", "%m/%d/%y", "%d.%m.%Y",
    "%b %d, %Y %I:%M %p", "%b %d, %Y", "%d %b %Y %I:%M %p",
    "%d %b %Y %H:%M", "%d %b %Y",
    "%B %d, %Y %I:%M %p", "%B %d, %Y", "%d %B %Y",
    "%a, %d %b %Y %H:%M:%S %z", "%A, %B %d, %Y",
    "%Y-%m-%d %I:%M %p", "%Y-%m-%dT%H:%M:%SZ",
]

ZH_RE = re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日(?:\s*(\d{1,2}):(\d{2})(?::(\d{2}))?)?$")


def try_strptime(s: str):
    for fmt in FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def normalize(s: str) -> str:
    s = s.strip()
    if not s:
        return ""
    m = ZH_RE.match(s)
    if m:
        y, mo, d, h, mi, se = m.groups()
        h = int(h) if h else 0
        mi = int(mi) if mi else 0
        se = int(se) if se else 0
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}T{h:02d}:{mi:02d}:{se:02d}"

    dt = try_strptime(s)
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def main() -> int:
    ap = argparse.ArgumentParser(description="多种常见日期格式统一输出为 ISO 8601")
    ap.add_argument("dates", nargs="*", help="待归一化的日期字符串")
    ap.add_argument("-f", "--file", help="逐行处理文件中的日期")
    args = ap.parse_args()

    items = list(args.dates)
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                items.extend(f.read().splitlines())
        except OSError as e:
            print(f"错误: 无法读取 {args.file}: {e}", file=sys.stderr)
            return 1
    if not items and not sys.stdin.isatty():
        items = sys.stdin.read().splitlines()
    if not items:
        ap.print_help()
        return 1

    ok = True
    for s in items:
        if not s.strip():
            continue
        r = normalize(s)
        if r:
            print(f"{s.strip()} -> {r}")
        else:
            print(f"{s.strip()} -> 无法识别", file=sys.stderr)
            ok = False
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
