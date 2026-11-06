#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文本日期抽取（date-scan）：从任意文本中按多模式抽取日期并去重排序，统一格式列出。

支持的日期写法：2025-03-14、2025/3/14、2025.03.14、2025年3月14日、3月14日（按当前年）、
14 Mar 2025、Mar 14, 2025、3/14/2025（先按月/日，不合法再按日/月）、3/14/25（两位年）。

用法:
  python date-scan.py 文本文件路径
  cat 文本文件 | python date-scan.py
  python date-scan.py -t "会议定在 2025/03/14，截止 2025-03-20"
  python date-scan.py -t "..." -f "%Y/%m/%d"      # 自定义输出格式
示例:
  python date-scan.py -t "a 2025-03-14 b 14 Mar 2025"   ->  2025-03-14（去重后仅一行）
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), "y-m-d"),
    (re.compile(r"\b(\d{4})/(\d{1,2})/(\d{1,2})\b"), "y-m-d"),
    (re.compile(r"\b(\d{4})\.(\d{1,2})\.(\d{1,2})\b"), "y-m-d"),
    (re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})[日号]"), "y-m-d"),
    (re.compile(r"(?<![\d年])(\d{1,2})月(\d{1,2})[日号]"), "m-d"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "a-b-y"),
    (re.compile(r"\b(\d{1,2})-(\d{1,2})-(\d{4})\b"), "a-b-y"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2})\b"), "a-b-yy"),
    (re.compile(r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{4})\b", re.IGNORECASE), "d-mon-y"),
    (re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.IGNORECASE), "mon-d-y"),
]


def candidates(kind, groups):
    """按模式类型给出 (年, 月, 日) 候选列表（年可为 None 表示用当前年）。"""
    g = groups
    if kind == "y-m-d":
        return [(int(g[0]), int(g[1]), int(g[2]))]
    if kind == "m-d":
        return [(None, int(g[0]), int(g[1]))]
    if kind == "a-b-y":
        a, b, y = int(g[0]), int(g[1]), int(g[2])
        return [(y, a, b), (y, b, a)]        # 先按 月/日，不合法再按 日/月
    if kind == "a-b-yy":
        a, b, yy = int(g[0]), int(g[1]), int(g[2])
        y = 2000 + yy if yy < 70 else 1900 + yy
        return [(y, a, b), (y, b, a)]
    if kind == "d-mon-y":
        return [(int(g[2]), MONTHS[g[1][:3].lower()], int(g[0]))]
    if kind == "mon-d-y":
        return [(int(g[2]), MONTHS[g[0][:3].lower()], int(g[1]))]
    return []


def to_date(ymds):
    """依次尝试候选元组，返回第一个合法 date；年缺失时用当前年。"""
    for y, m, d in ymds:
        if y is None:
            y = datetime.now().year
        try:
            return date(y, m, d)
        except ValueError:
            continue
    return None


def scan(text: str):
    """返回 [(date, 命中文本), ...]，已按日期去重（同一日期保留首个命中）。"""
    found = {}
    for rx, kind in PATTERNS:
        for m in rx.finditer(text):
            dt = to_date(candidates(kind, m.groups()))
            if dt is not None and dt not in found:
                found[dt] = m.group(0)
    return sorted(found.items())


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(
        description="文本日期抽取：按多模式抽取日期并去重排序，统一格式列出。")
    ap.add_argument("file", nargs="?", help="输入文本文件；缺省或为 - 时读 stdin")
    ap.add_argument("-t", "--text", help="直接传入待扫描文本")
    ap.add_argument("-f", "--format", default="%Y-%m-%d",
                    help="输出 strftime 格式（默认 %%Y-%%m-%%d）")
    ap.add_argument("-s", "--source", action="store_true",
                    help="同时显示命中的原文")
    args = ap.parse_args(argv)

    if args.text is not None:
        text = args.text
    else:
        if args.file and args.file != "-":
            try:
                with open(args.file, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError as exc:
                print(f"错误：无法读取文件 {args.file!r}: {exc}", file=sys.stderr)
                return 2
        else:
            text = sys.stdin.read()

    items = scan(text)
    if not items:
        print("（未发现日期）")
        return 0
    try:
        for dt, src in items:
            line = dt.strftime(args.format)
            print(f"{line}\t# {src}" if args.source else line)
    except (ValueError, TypeError) as exc:
        print(f"错误：输出格式无效：{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
