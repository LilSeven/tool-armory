#!/usr/bin/env python3
r"""syslog解析统计 (syslog-stats): 解析 syslog 格式行, 按主机、进程、级别维度统计分布。

用途:
    读入 syslog 文本(文件或标准输入), 解析两类常见格式:
      RFC3164:  "<PRI>Mmm dd hh:mm:ss host tag[pid]: message"
                如 "<30>Nov  2 10:00:01 web-01 nginx[1234]: GET / 200"
      ISO 变体: "YYYY-MM-DDThh:mm:ss[.frac][Z|+hh:mm] [PRI] host tag[pid]: message"
    统计并输出四个维度的分布表: 按主机(hostname)、按进程(tag, 不含 pid)、
    按级别(severity, 取自 PRI; 无 PRI 时按消息关键字推断, 推断不出记 unknown)、
    按设施(facility); 无法解析的行计入 unparsed, 可用 --show-unparsed 查看。

示例命令:
    python -I syslog-stats.py /var/log/syslog
    python -I syslog-stats.py --top 5 --sort name messages.log auth.log
    python -I syslog-stats.py --show-unparsed syslog.log
    cat syslog.log | python -I syslog-stats.py --json

退出码: 0 成功; 2 参数错误或文件读取失败。
"""

import argparse
import json
import re
import sys
from collections import Counter

SEVERITIES = ["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"]
FACILITIES = ["kern", "user", "mail", "daemon", "auth", "syslog", "lpr", "news",
              "uucp", "clock", "authpriv", "ftp", "ntp", "audit", "alert", "clock2",
              "local0", "local1", "local2", "local3", "local4", "local5", "local6", "local7"]

RFC3164_RE = re.compile(
    r"^(?:<(?P<pri>\d{1,3})>)?\s*"
    r"[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+"
    r"(?P<host>\S+)\s+"
    r"(?P<app>[^\s:\[]+)(?:\[\d+\])?:\s?"
    r"(?P<msg>.*)$")

ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\s+"
    r"(?:<(?P<pri>\d{1,3})>)?\s*"
    r"(?P<host>\S+)\s+"
    r"(?P<app>[^\s:\[]+)(?:\[\d+\])?:\s?"
    r"(?P<msg>.*)$")

KEYWORD_LEVELS = [
    (re.compile(r"\b(?:emerg(?:ency)?|panic)\b", re.I), "emerg"),
    (re.compile(r"\b(?:fatal|critical)\b", re.I), "crit"),
    (re.compile(r"\b(?:err(?:or)?|fail(?:ed|ure)?)\b", re.I), "err"),
    (re.compile(r"\bwarn(?:ing)?\b", re.I), "warning"),
    (re.compile(r"\bnotice\b", re.I), "notice"),
    (re.compile(r"\bdebug\b", re.I), "debug"),
    (re.compile(r"\binfo\b", re.I), "info"),
]


def parse_line(line):
    """解析一行, 返回 (host, app, severity, facility); 不匹配返回 None。"""
    mobj = RFC3164_RE.match(line) or ISO_RE.match(line)
    if not mobj:
        return None
    host, app, msg = mobj.group("host"), mobj.group("app"), mobj.group("msg")
    pri_s = mobj.group("pri")
    if pri_s is not None:
        pri = int(pri_s)
        if 0 <= pri <= 191:
            return host, app, SEVERITIES[pri & 7], FACILITIES[pri >> 3]
        return host, app, "unknown", "invalid"
    for rx, name in KEYWORD_LEVELS:
        if rx.search(msg):
            return host, app, name, "no-pri"
    return host, app, "unknown", "no-pri"


def stream_setup():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def iter_lines(paths):
    if not paths:
        for line in sys.stdin:
            yield line
        return
    for path in paths:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                yield line


def print_table(title, counter, base, sort, top):
    print(f"\n-- {title} --")
    if not counter:
        print("  (无数据)")
        return
    items = counter.most_common() if sort == "count" else sorted(counter.items())
    if top > 0:
        items = items[:top]
    for name, cnt in items:
        pct = (cnt / base * 100) if base else 0.0
        bar = "#" * max(1, min(20, round(pct / 5)))
        print(f"  {cnt:>6}  {pct:5.1f}%  {bar:<20}  {name}")


def main(argv=None):
    stream_setup()
    parser = argparse.ArgumentParser(
        prog="syslog-stats",
        description="解析 syslog 格式行, 按主机、进程、级别维度统计分布。")
    parser.add_argument("files", nargs="*", help="syslog 文件; 缺省读标准输入")
    parser.add_argument("--top", type=int, default=10, metavar="N",
                        help="每个维度最多显示 N 行 (默认 10, <=0 不限)")
    parser.add_argument("--sort", choices=("count", "name"), default="count",
                        help="排序方式 (默认按次数降序)")
    parser.add_argument("--show-unparsed", action="store_true", help="列出无法解析的行")
    parser.add_argument("--json", action="store_true", dest="as_json", help="以 JSON 输出统计")
    args = parser.parse_args(argv)

    hosts, apps, sevs, facs = Counter(), Counter(), Counter(), Counter()
    parsed = unparsed = 0
    bad_lines = []
    try:
        for raw in iter_lines(args.files):
            line = raw.rstrip("\r\n")
            if not line.strip():
                continue
            rec = parse_line(line)
            if rec is None:
                unparsed += 1
                bad_lines.append(line)
            else:
                host, app, sev, fac = rec
                parsed += 1
                hosts[host] += 1
                apps[app] += 1
                sevs[sev] += 1
                facs[fac] += 1
    except OSError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    if args.as_json:
        print(json.dumps({
            "total": parsed + unparsed, "parsed": parsed, "unparsed": unparsed,
            "by_host": dict(hosts.most_common()),
            "by_app": dict(apps.most_common()),
            "by_severity": dict(sevs.most_common()),
            "by_facility": dict(facs.most_common()),
        }, ensure_ascii=False, indent=2))
        return 0

    print("== syslog 解析统计 ==")
    print(f"总行数: {parsed + unparsed}   解析成功: {parsed}   未解析: {unparsed}")
    print_table("按主机 (hostname)", hosts, parsed, args.sort, args.top)
    print_table("按进程 (tag)", apps, parsed, args.sort, args.top)
    print_table("按级别 (severity)", sevs, parsed, args.sort, args.top)
    print_table("按设施 (facility)", facs, parsed, args.sort, args.top)
    if args.show_unparsed and bad_lines:
        print("\n-- 未解析行 (最多显示 50 条) --")
        for line in bad_lines[:50]:
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
