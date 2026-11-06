#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件大小分布直方图 (size-histogram)

把目录(或文件)中的文件按大小分桶(0B、<1KB、1-10KB、…、>=1GB)，
输出分布直方图，以及文件数、总大小、均值、中位数、极值等摘要。

用法:
    python size-histogram.py <目录>
    python size-histogram.py <目录或文件>...
    python size-histogram.py <目录> --width 50
    python size-histogram.py <目录> --json

示例:
    python size-histogram.py D:/downloads
    python size-histogram.py D:/videos --width 60
"""
import argparse
import json
import os
import statistics
import sys
import unicodedata

KB = 1024
BUCKETS = [
    ("0B", 1),
    ("<1KB", KB),
    ("1KB-10KB", 10 * KB),
    ("10KB-100KB", 100 * KB),
    ("100KB-1MB", KB ** 2),
    ("1MB-10MB", 10 * KB ** 2),
    ("10MB-100MB", 100 * KB ** 2),
    ("100MB-1GB", KB ** 3),
    (">=1GB", None),
]


def human(n) -> str:
    """字节数 -> 人类可读字符串, 如 15.3 GB; 支持负数。"""
    n = float(n)
    neg = n < 0
    n = abs(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if n < 1024 or unit == "PB":
            text = f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
            return ("-" + text) if neg else text
        n /= 1024.0
    return f"{n:,.1f} PB"


def dwidth(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def lpad(s: str, width: int) -> str:
    return " " * max(0, width - dwidth(s)) + s


def bucket_index(size: int) -> int:
    for i, (_label, upper) in enumerate(BUCKETS):
        if upper is None or size < upper:
            return i
    return len(BUCKETS) - 1


def collect(paths):
    """收集所有文件大小; 返回 (sizes, skipped, missing)。"""
    sizes, skipped, missing = [], 0, []
    for p in paths:
        if os.path.isdir(p):
            for dirpath, _dirs, files in os.walk(p, onerror=lambda e: None):
                for name in files:
                    try:
                        sizes.append(os.lstat(os.path.join(dirpath, name)).st_size)
                    except OSError:
                        skipped += 1
        elif os.path.lexists(p):
            try:
                sizes.append(os.lstat(p).st_size)
            except OSError:
                skipped += 1
        else:
            missing.append(p)
    return sizes, skipped, missing


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="size-histogram",
        description="按大小分桶统计文件分布, 输出直方图与均值/中位数/极值摘要")
    ap.add_argument("paths", nargs="+", help="目录或文件(可多个)")
    ap.add_argument("--width", type=int, default=40, metavar="N",
                    help="直方图条最大宽度(默认 40)")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    sizes, skipped, missing = collect(args.paths)
    for p in missing:
        print(f"[跳过] 路径不存在: {p}", file=sys.stderr)

    counts = [0] * len(BUCKETS)
    bytes_by = [0] * len(BUCKETS)
    for s in sizes:
        i = bucket_index(s)
        counts[i] += 1
        bytes_by[i] += s

    n = len(sizes)
    total = sum(sizes)

    if args.json:
        print(json.dumps({
            "files": n,
            "skipped": skipped + len(missing),
            "total_bytes": total,
            "mean_bytes": round(total / n, 1) if n else None,
            "median_bytes": statistics.median(sizes) if n else None,
            "min_bytes": min(sizes) if n else None,
            "max_bytes": max(sizes) if n else None,
            "buckets": [
                {"label": label, "count": counts[i], "bytes": bytes_by[i],
                 "pct": round(counts[i] / n * 100, 1) if n else 0.0}
                for i, (label, _u) in enumerate(BUCKETS)
            ],
        }, ensure_ascii=False, indent=2))
        return 0

    if skipped + len(missing):
        print(f"(跳过 {skipped + len(missing)} 个无法读取/不存在的路径)")
    if n == 0:
        print("未找到任何文件")
        return 0

    label_w = max(len(lbl) for lbl, _u in BUCKETS)
    print(f"文件总数: {n:,}    总大小: {human(total)}")
    print(f"均值: {human(total / n)}    中位数: {human(statistics.median(sizes))}")
    print(f"最小: {human(min(sizes))}    最大: {human(max(sizes))}")
    print()
    print(f"{'大小桶':<{label_w}}  {lpad('文件数', 9)}  {lpad('占比', 7)}  直方图")
    maxc = max(counts)
    for i, (label, _u) in enumerate(BUCKETS):
        bar = "#" * (round(counts[i] / maxc * args.width) if maxc else 0)
        pct = counts[i] / n * 100
        print(f"{label:<{label_w}}  {counts[i]:>9,}  {pct:>6.1f}%  {bar}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
