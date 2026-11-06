#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""访问日志转 CSV (log2csv)。

用途:
    解析 nginx / apache 「combined」格式访问日志（兼容缺少 referer/UA
    的 common 格式行），输出 CSV，字段含 IP、时间、方法、路径、协议、
    状态码、响应字节数、Referer、User-Agent。

示例命令:
    python -I log2csv.py access.log -o access.csv
    python -I log2csv.py access.log --no-header --status 200,404
    cat access.log | python -I log2csv.py - --time-format "%Y-%m-%d %H:%M:%S"
    python -I log2csv.py --self-test
"""
import argparse
import csv
import io
import re
import sys
from datetime import datetime

# combined: ip ident user [time] "request" status size "referer" "ua"
LINE_RE = re.compile(
    r'^(?P<ip>\S+)\s+(?P<ident>\S+)\s+(?P<user>\S+)\s+'
    r'\[(?P<time>[^\]]+)\]\s+"(?P<request>[^"]*)"\s+'
    r'(?P<status>\d{3}|-)\s+(?P<size>\d+|-)'
    r'(?:\s+"(?P<referer>[^"]*)"\s+"(?P<ua>[^"]*)")?\s*$')

FIELDS = ["ip", "time", "method", "path", "protocol",
          "status", "size", "referer", "user_agent"]


def parse_line(line: str):
    """解析单行日志，失败返回 None。request 拆为 method/path/protocol。"""
    m = LINE_RE.match(line.rstrip("\r\n"))
    if not m:
        return None
    d = m.groupdict()
    method = path = protocol = ""
    req = d["request"]
    parts = req.split()
    if len(parts) == 3:
        method, path, protocol = parts
    elif len(parts) == 1 and parts[0]:
        path = parts[0]
    status = d["status"] if d["status"] != "-" else ""
    size = d["size"] if d["size"] != "-" else "0"
    return {
        "ip": d["ip"],
        "time": d["time"],
        "method": method,
        "path": path,
        "protocol": protocol,
        "status": status,
        "size": size,
        "referer": d.get("referer") or "",
        "user_agent": d.get("ua") or "",
    }


def convert_time(raw: str, fmt: str) -> str:
    """把 '10/Oct/2023:13:55:36 +0800' 转成目标格式，失败保留原样。"""
    if fmt == "raw" or not raw:
        return raw
    try:
        dt = datetime.strptime(raw, "%d/%b/%Y:%H:%M:%S %z")
        return dt.strftime(fmt)
    except ValueError:
        return raw


def main(argv=None):
    ap = argparse.ArgumentParser(description="nginx/apache 访问日志转 CSV")
    ap.add_argument("input", nargs="?", help="日志文件；为 - 时读 stdin")
    ap.add_argument("-o", "--output", help="输出 CSV 文件（缺省 stdout）")
    ap.add_argument("--no-header", action="store_true", help="不写表头行")
    ap.add_argument("--time-format", default="raw", metavar="FMT",
                    help="时间输出格式，raw=原样保留，其他用 strftime 格式")
    ap.add_argument("--status", help="仅保留这些状态码，逗号分隔，如 200,404")
    ap.add_argument("--self-test", action="store_true", help="运行内置自测")
    args = ap.parse_args(argv)

    if args.self_test:
        sample = [
            '192.168.1.10 - alice [10/Oct/2023:13:55:36 +0800] "GET /index.html HTTP/1.1" 200 2326 "https://ref.example/" "Mozilla/5.0"',
            '10.0.0.5 - - [10/Oct/2023:13:55:37 +0800] "POST /api/submit HTTP/1.1" 404 0 "-" "curl/8.0"',
            '10.0.0.6 - - [10/Oct/2023:13:55:38 +0800] "GET /a.html HTTP/1.1" 200 512',  # common 格式
            'broken line',
        ]
        rows = [parse_line(l) for l in sample]
        assert rows[0]["ip"] == "192.168.1.10"
        assert rows[0]["path"] == "/index.html" and rows[0]["status"] == "200"
        assert rows[0]["referer"] == "https://ref.example/"
        assert rows[1]["method"] == "POST" and rows[1]["status"] == "404"
        assert rows[2]["path"] == "/a.html" and rows[2]["referer"] == ""
        assert rows[3] is None
        t = convert_time("10/Oct/2023:13:55:36 +0800", "%Y-%m-%d %H:%M:%S")
        assert t == "2023-10-10 13:55:36", t
        print("self-test OK")
        return 0

    if not args.input or args.input == "-":
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        lines = sys.stdin.read().splitlines()
    else:
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()

    keep_status = set(s.strip() for s in args.status.split(",")) if args.status else None

    out = io.StringIO()
    w = csv.writer(out)
    if not args.no_header:
        w.writerow(FIELDS)
    n_ok = n_bad = 0
    for line in lines:
        if not line.strip():
            continue
        row = parse_line(line)
        if row is None:
            n_bad += 1
            continue
        if keep_status is not None and row["status"] not in keep_status:
            continue
        row["time"] = convert_time(row["time"], args.time_format)
        w.writerow([row[k] for k in FIELDS])
        n_ok += 1

    if args.output:
        with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
            f.write(out.getvalue())
        print(f"[log2csv] 解析 {n_ok} 行 -> {args.output}；未识别 {n_bad} 行", file=sys.stderr)
    else:
        sys.stdout.write(out.getvalue())
        if n_bad:
            print(f"[log2csv] 未识别 {n_bad} 行", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
