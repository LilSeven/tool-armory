#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""访问TopN统计 —— 从访问日志统计 Top N 的 IP、URL、User-Agent。

解析 nginx / apache 的 common 或 combined 格式访问日志，统计指定维度
(ip / url / ua / method / status) 的出现频次，按次数降序输出前 N 条及占比。

示例命令:
    python access-top-n.py access.log
    python access-top-n.py access.log -n 20
    python access-top-n.py access.log --field ip --field status -n 5

输入行示例 (combined 格式):
    203.0.113.7 - - [10/Oct/2023:13:55:36 +0800] "GET /index.html HTTP/1.1" 200 2326 "-" "curl/8.0.1"
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter

# combined / common 格式: ip ident user [time] "request" status size ["referer" "ua"]
LINE_RE = re.compile(
    r'^(?P<ip>\S+)\s+\S+\s+\S+\s+\[[^\]]*\]\s+'
    r'"(?P<request>[^"]*)"\s+'
    r'(?P<status>\d{3})\s+(?P<size>\S+)'
    r'(?:\s+"(?P<ref>[^"]*)"\s+"(?P<ua>[^"]*)")?\s*$'
)
REQUEST_RE = re.compile(r'^(?P<method>[A-Z]+)\s+(?P<url>\S+)(?:\s+(?P<proto>[^"\s]+))?$')

FIELDS = ("ip", "url", "ua", "method", "status")
FIELD_TITLES = {"ip": "IP", "url": "URL", "ua": "User-Agent",
                "method": "Method", "status": "Status"}


def setup_stdio() -> None:
    """在 Windows 控制器/管道下保证中文输出不因编码报错。"""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_line(line: str):
    """解析一行访问日志，返回字段字典；不匹配返回 None。"""
    m = LINE_RE.match(line)
    if not m:
        return None
    d = m.groupdict()
    req = REQUEST_RE.match(d.get("request") or "")
    if req:
        d["method"] = req.group("method")
        d["url"] = req.group("url")
    else:
        d["method"] = "-"
        d["url"] = (d.get("request") or "-").strip() or "-"
    d["ua"] = (d.get("ua") or "-").strip() or "-"
    d["ip"] = d["ip"].strip()
    d["status"] = d["status"].strip()
    return d


def main(argv=None) -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(
        description="从访问日志统计 Top N 的 IP / URL / User-Agent (nginx/apache common 或 combined 格式)")
    ap.add_argument("logfile", help="访问日志文件路径")
    ap.add_argument("-n", "--top", type=int, default=10, help="每个维度输出的条数 (默认 10)")
    ap.add_argument("--field", action="append", choices=FIELDS,
                    default=["ip", "url", "ua"],
                    help="统计维度，可多次指定 (默认: ip url ua)")
    ap.add_argument("--encoding", default="utf-8", help="日志文件编码 (默认 utf-8)")
    args = ap.parse_args(argv)

    counters = {f: Counter() for f in args.field}
    total = parsed = 0
    try:
        with open(args.logfile, "r", encoding=args.encoding, errors="replace") as f:
            for raw in f:
                line = raw.rstrip("\r\n")
                if not line.strip():
                    continue
                total += 1
                d = parse_line(line)
                if d is None:
                    continue
                parsed += 1
                for fld in counters:
                    counters[fld][d[fld]] += 1
    except OSError as e:
        print(f"错误: 无法读取 {args.logfile}: {e}", file=sys.stderr)
        return 2

    print(f"日志: {args.logfile}   总行数: {total}   已解析: {parsed}   未解析: {total - parsed}")
    for fld in args.field:
        c = counters[fld]
        grand = sum(c.values())
        print(f"\n== Top {args.top} {FIELD_TITLES[fld]} ==")
        if not c:
            print("  (无数据)")
            continue
        for i, (key, cnt) in enumerate(c.most_common(args.top), 1):
            show = key if len(key) <= 66 else key[:63] + "..."
            pct = cnt / grand * 100 if grand else 0.0
            print(f"  {i:>2}. {show:<66} {cnt:>8} 次  {pct:5.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
