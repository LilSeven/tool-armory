#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""异常频次排行 —— 统计日志中各异常类型/错误码出现频次并排序输出。

三种模式:
    exception (默认): 统计以 Exception/Error/Throwable/Fault 结尾的异常类名;
    code:             统计 `code=XXX` / `errno:XXX` / `status=XXX` 等错误码;
    --pattern RE:     自定义正则，取第 1 个分组作为统计键（无分组则取整条匹配）。

示例命令:
    python exception-top.py app.log
    python exception-top.py app.log --mode code -n 20
    python exception-top.py app.log --pattern 'GET /api/(\S+)'
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter

EXC_RE = re.compile(
    r'(?<![\w.$])((?:[A-Za-z_$][\w$]*\.)*[A-Z][A-Za-z0-9_$]*'
    r'(?:Exception|Error|Throwable|Fault)\b)'
)
CODE_RE = re.compile(
    r'\b(?:err(?:or)?[\s_.-]?code|errno|code|status)\s*[=:]\s*["\']?'
    r'([A-Za-z0-9][A-Za-z0-9_.+-]{0,15})["\']?',
    re.IGNORECASE,
)


def setup_stdio() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def build_pattern(mode: str, custom: str):
    if custom:
        return re.compile(custom), "custom"
    if mode == "code":
        return CODE_RE, "错误码"
    return EXC_RE, "异常类型"


def main(argv=None) -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(
        description="统计日志中各异常类型/错误码出现频次并按次数排序输出")
    ap.add_argument("logfile", help="日志文件路径")
    ap.add_argument("--mode", choices=("exception", "code"), default="exception",
                    help="统计模式 (默认 exception)")
    ap.add_argument("-n", "--top", type=int, default=10, help="输出的条数 (默认 10)")
    ap.add_argument("--pattern", help="自定义正则 (统计键=第1个分组，无分组则整条匹配)")
    ap.add_argument("--per-line", action="store_true", help="每行最多计 1 次 (默认逐个匹配计数)")
    ap.add_argument("--encoding", default="utf-8", help="日志文件编码 (默认 utf-8)")
    args = ap.parse_args(argv)

    try:
        pat, mode_name = build_pattern(args.mode, args.pattern)
    except re.error as e:
        print(f"错误: 正则无效: {e}", file=sys.stderr)
        return 2

    counts: Counter = Counter()
    matched_lines = 0
    try:
        with open(args.logfile, "r", encoding=args.encoding, errors="replace") as f:
            for raw in f:
                line = raw.rstrip("\r\n")
                ms = list(pat.finditer(line))
                if not ms:
                    continue
                matched_lines += 1
                if args.per_line:
                    ms = ms[:1]
                for m in ms:
                    key = (m.group(1) if m.groups() else m.group(0)).strip()
                    if key:
                        counts[key] += 1
    except OSError as e:
        print(f"错误: 无法读取 {args.logfile}: {e}", file=sys.stderr)
        return 2

    total = sum(counts.values())
    print(f"文件: {args.logfile}   模式: {mode_name}   匹配行数: {matched_lines}   总匹配: {total}")
    print(f"\n== Top {args.top} ==")
    if not counts:
        print("  (无匹配)")
        return 0
    for i, (key, cnt) in enumerate(counts.most_common(args.top), 1):
        show = key if len(key) <= 56 else key[:53] + "..."
        pct = cnt / total * 100 if total else 0.0
        print(f"  {i:>2}. {show:<56} {cnt:>6} 次  {pct:5.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
