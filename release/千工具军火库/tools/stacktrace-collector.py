#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""堆栈提取器 —— 从日志中把异常头与缩进堆栈行组装成完整堆栈块并逐个输出。

识别异常头（含 *Exception/*Error/*Throwable/*Fault 类名的行，或
`Traceback (most recent call last):`），并把其后的缩进堆栈行（`\\tat ...`、
`  File "..."`）、`Caused by:` 行以及 Traceback 末尾的异常声明行聚合为
完整堆栈块，用分隔线逐个输出到 stdout（或 --out 指定的文件）。

示例命令:
    python stacktrace-collector.py app.log
    python stacktrace-collector.py app.log --out stacks.txt
    python stacktrace-collector.py app.log --encoding gbk
"""
from __future__ import annotations

import argparse
import re
import sys

# 异常头: 异常类名（可带包名前缀）或 Python 的 Traceback 头
HEADER_RE = re.compile(
    r'(?<![\w.$])'
    r'(?:(?:[A-Za-z_$][\w$]*\.)*[A-Z][A-Za-z0-9_$]*(?:Exception|Error|Throwable|Fault)\b'
    r'|Traceback \(most recent call last\):?)'
)
CAUSED_BY_RE = re.compile(r'\bCaused by:\s')
# Traceback 末行的异常声明: 顶格的 `XXXError:` / `YYYException` 行
FINAL_RE = re.compile(
    r'^(?:[A-Za-z_$][\w$.]*\.)*[A-Z][A-Za-z0-9_$]*(?:Exception|Error|Throwable|Fault)\b(?::|$)'
)


def setup_stdio() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def is_stack_line(line: str) -> bool:
    """判断是否属于堆栈块内部行：缩进行 / Caused by / 顶格异常声明。"""
    s = line.strip()
    if not s:
        return False
    if line[:1] in (" ", "\t"):
        return True
    if CAUSED_BY_RE.search(s):
        return True
    if s.startswith("at ") or s.startswith('File "'):
        return True
    return bool(FINAL_RE.match(s))


def collect(lines):
    """把日志行列表组装成堆栈块列表（每块为行列表）。"""
    blocks = []
    cur = None
    for line in lines:
        if cur is None:
            if HEADER_RE.search(line):
                cur = [line]
            continue
        # 已在堆栈块内
        if not line.strip():
            blocks.append(cur)
            cur = None
            continue
        if is_stack_line(line):
            cur.append(line)
            continue
        # 非缩进、非堆栈行: 结束当前块，并检查它自身是否是新的异常头
        blocks.append(cur)
        cur = None
        if HEADER_RE.search(line):
            cur = [line]
    if cur is not None:
        blocks.append(cur)
    return blocks


def main(argv=None) -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(
        description="从日志中提取完整异常堆栈块（异常头 + 缩进堆栈行 + Caused by）并逐个输出")
    ap.add_argument("logfile", help="日志文件路径")
    ap.add_argument("--out", help="结果写入指定文件 (缺省输出到 stdout)")
    ap.add_argument("--encoding", default="utf-8", help="日志文件编码 (默认 utf-8)")
    args = ap.parse_args(argv)

    try:
        with open(args.logfile, "r", encoding=args.encoding, errors="replace") as f:
            lines = f.read().splitlines()
    except OSError as e:
        print(f"错误: 无法读取 {args.logfile}: {e}", file=sys.stderr)
        return 2

    blocks = collect(lines)

    out = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    try:
        for i, block in enumerate(blocks, 1):
            print(f"---- 堆栈块 #{i} ({len(block)} 行) ----", file=out)
            for l in block:
                print(l, file=out)
        if not blocks:
            print("(未发现堆栈块)", file=out)
    finally:
        if out is not sys.stdout:
            out.close()
    print(f"共提取 {len(blocks)} 个堆栈块。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
