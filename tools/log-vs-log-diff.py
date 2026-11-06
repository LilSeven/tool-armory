#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日志对比 —— 比较两份日志的级别分布与错误模板集合差异，报告新增/消失的错误。

对两份日志分别统计日志级别 (TRACE/DEBUG/INFO/NOTICE/WARN/ERROR/CRITICAL/FATAL)
的行数分布；并将 ERROR 及以上（可用 --include-warn 纳入 WARN）的行归一化为
"错误模板"（时间戳/UUID/IP地址/十六进制/引号内容/数字 替换为占位符），
对比两份模板集合，报告 NEW 中新增与 OLD 中消失的错误模板。

示例命令:
    python log-vs-log-diff.py old.log new.log
    python log-vs-log-diff.py old.log new.log --include-warn
    python log-vs-log-diff.py old.log new.log --fail-on-diff   # 有差异则退出码 1 (可用于 CI)
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter

# 级别词按长度降序排列，避免 WARNING 被 WARN 截断匹配；区分大小写，只认大写常见写法
LEVEL_RE = re.compile(r'\b(TRACE|DEBUG|INFO|NOTICE|WARNING|WARN|ERROR|CRITICAL|FATAL|ERR)\b')
CANON = {"WARNING": "WARN", "ERR": "ERROR"}
ERROR_LEVELS = {"ERROR", "CRITICAL", "FATAL"}

# 归一化规则：按顺序替换，先特殊后一般
NORMALIZE_RULES = [
    (re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?'), '<TS>'),
    (re.compile(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'), '<UUID>'),
    (re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b'), '<ADDR>'),
    (re.compile(r'\b0[xX][0-9a-fA-F]+\b'), '<HEX>'),
    (re.compile(r'"[^"]*"|\'[^\']*\''), '<Q>'),
    (re.compile(r'\b\d+(?:\.\d+)?\b'), '<N>'),
    (re.compile(r'\s+'), ' '),
]


def setup_stdio() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def level_of(line: str) -> str:
    m = LEVEL_RE.search(line)
    if not m:
        return "OTHER"
    lv = m.group(1)
    return CANON.get(lv, lv)


def normalize(line: str) -> str:
    for pat, repl in NORMALIZE_RULES:
        line = pat.sub(repl, line)
    return line.strip()


def scan(path: str, encoding: str, include_warn: bool):
    """返回 (级别计数, 错误模板计数)。"""
    levels: Counter = Counter()
    err_templates: Counter = Counter()
    with open(path, "r", encoding=encoding, errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            if not line.strip():
                continue
            lv = level_of(line)
            levels[lv] += 1
            if lv in ERROR_LEVELS or (include_warn and lv == "WARN"):
                err_templates[normalize(line)] += 1
    return levels, err_templates


def main(argv=None) -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(
        description="比较两份日志的级别分布与错误模板集合差异，报告新增/消失的错误")
    ap.add_argument("old_log", help="旧日志文件")
    ap.add_argument("new_log", help="新日志文件")
    ap.add_argument("--include-warn", action="store_true", help="把 WARN 也纳入错误模板对比")
    ap.add_argument("--encoding", default="utf-8", help="日志文件编码 (默认 utf-8)")
    ap.add_argument("--fail-on-diff", action="store_true", help="存在差异时以退出码 1 结束")
    args = ap.parse_args(argv)

    try:
        old_levels, old_err = scan(args.old_log, args.encoding, args.include_warn)
        new_levels, new_err = scan(args.new_log, args.encoding, args.include_warn)
    except OSError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2

    print(f"旧日志: {args.old_log}   新日志: {args.new_log}")
    print("\n== 级别分布 ==")
    print(f"  {'LEVEL':<10}{'OLD':>8}{'NEW':>8}{'DELTA':>8}")
    for lv in sorted(set(old_levels) | set(new_levels)):
        o = old_levels.get(lv, 0)
        n = new_levels.get(lv, 0)
        print(f"  {lv:<10}{o:>8}{n:>8}{n - o:>+8}")

    added = {t: c for t, c in new_err.items() if t not in old_err}
    gone = {t: c for t, c in old_err.items() if t not in new_err}

    print(f"\n== 新增错误模板 (仅 NEW 出现): {len(added)} 种 ==")
    if not added:
        print("  (无)")
    for t, c in sorted(added.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  + {c:>4} 次  {t[:110]}")

    print(f"\n== 消失错误模板 (仅 OLD 出现): {len(gone)} 种 ==")
    if not gone:
        print("  (无)")
    for t, c in sorted(gone.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  - {c:>4} 次  {t[:110]}")

    if not added and not gone:
        print("\n结论: 错误模板集合一致。")
    return 1 if (args.fail_on_diff and (added or gone)) else 0


if __name__ == "__main__":
    sys.exit(main())
