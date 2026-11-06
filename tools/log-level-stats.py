#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""log-level-stats — 日志级别统计。

识别每一行日志的级别 (TRACE/DEBUG/INFO/NOTICE/WARN/ERROR/FATAL)，
统计各级别出现次数与占比，用于快速掌握日志的健康状况。

识别规则:
  * 优先整词匹配大写级别，如 "ERROR"、"[INFO]"、"level=warn"；
  * 大写未命中时退化为忽略大小写匹配；
  * WARNING 归并为 WARN，CRITICAL 归并为 FATAL，ERR 归并为 ERROR；
  * 未识别出级别的行计入"未识别"。

用法:
  python log-level-stats.py <日志文件|-> [--top N] [--json]

示例:
  python log-level-stats.py app.log
  python log-level-stats.py app.log --top 3
  tail -n 500 app.log | python log-level-stats.py - --json
"""

import argparse
import json
import re
import sys

LEVEL_RE = re.compile(
    r"\b(TRACE|DEBUG|INFO|NOTICE|WARNING|WARN|ERROR|ERR|FATAL|CRITICAL)\b")
LEVEL_RE_LOOSE = re.compile(LEVEL_RE.pattern, re.IGNORECASE)
LEVEL_SYNONYM = {"WARNING": "WARN", "ERR": "ERROR", "CRITICAL": "FATAL"}
LEVEL_ORDER = ("TRACE", "DEBUG", "INFO", "NOTICE", "WARN", "ERROR", "FATAL")


def normalize_level(name):
    name = name.upper()
    return LEVEL_SYNONYM.get(name, name)


def detect_level(line):
    """从一行日志中识别级别，返回规范化级别名，识别不出返回 None。"""
    m = LEVEL_RE.search(line)
    if m:
        return normalize_level(m.group(1))
    m = LEVEL_RE_LOOSE.search(line)
    if m:
        return normalize_level(m.group(1))
    return None


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        description="识别日志行级别并统计各级别出现次数与占比")
    ap.add_argument("file", help="日志文件路径, 传 - 读标准输入")
    ap.add_argument("--top", type=int, default=0,
                    help="只显示次数最多的前 N 个级别 (默认 0=全部)")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = ap.parse_args(argv)

    if args.file == "-":
        if not sys.stdin.isatty():
            try:
                sys.stdin.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        fh, need_close = sys.stdin, False
    else:
        try:
            fh = open(args.file, "r", encoding="utf-8", errors="replace")
        except OSError as e:
            print("错误: 无法打开 {}: {}".format(args.file, e), file=sys.stderr)
            return 2
        need_close = True

    total = 0
    matched = 0
    counts = {}
    try:
        for line in fh:
            total += 1
            lv = detect_level(line)
            if lv is None:
                continue
            matched += 1
            counts[lv] = counts.get(lv, 0) + 1
    finally:
        if need_close:
            fh.close()

    def sort_key(item):
        lv, cnt = item
        order = LEVEL_ORDER.index(lv) if lv in LEVEL_ORDER else len(LEVEL_ORDER)
        return (-cnt, order, lv)

    items = sorted(counts.items(), key=sort_key)
    shown = items[:args.top] if args.top > 0 else items

    if args.json:
        data = {
            "file": args.file,
            "total_lines": total,
            "recognized_lines": matched,
            "unrecognized_lines": total - matched,
            "levels": [
                {"level": lv, "count": c,
                 "percent": round(c * 100.0 / matched, 1) if matched else 0.0}
                for lv, c in shown
            ],
        }
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print("文件: {}  总行数: {}  识别到级别: {} 行  未识别: {} 行".format(
        args.file, total, matched, total - matched))
    if args.top > 0 and len(items) > len(shown):
        rest = sum(c for _, c in items[len(shown):])
        print("提示: 仅显示前 {} 个级别, 其余 {} 个级别共 {} 行未显示".format(
            args.top, len(items) - len(shown), rest))
    print("{:<10}{:>10}{:>10}".format("LEVEL", "COUNT", "PERCENT"))
    for lv, c in shown:
        pct = c * 100.0 / matched if matched else 0.0
        print("{:<10}{:>10}{:>9.1f}%".format(lv, c, pct))
    return 0


if __name__ == "__main__":
    sys.exit(main())
