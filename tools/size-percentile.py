#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""size-percentile — 文件大小分位统计。

递归收集目录内所有文件的大小, 计算均值与 P10/P25/P50(中位数)/P75/P90/P95/P99
等分位数, 并按数量级分桶画出文件数直方图, 刻画目录内文件大小分布形态。
分位数采用线性插值法(与 numpy 默认及 statistics 的 inclusive 方法一致)。

示例:
    python -I size-percentile.py D:\\logs        # 统计表 + 直方图
    python -I size-percentile.py . --json        # JSON 输出(数值单位: 字节)
    python -I size-percentile.py . --no-hist     # 不显示直方图

退出码: 0 成功; 1 目录不存在或目录内没有普通文件。
"""

import argparse
import json
import math
import os
import sys

BUCKETS = (
    ("<1K", 0, 1024),
    ("1K-4K", 1024, 4 * 1024),
    ("4K-16K", 4 * 1024, 16 * 1024),
    ("16K-64K", 16 * 1024, 64 * 1024),
    ("64K-256K", 64 * 1024, 256 * 1024),
    ("256K-1M", 256 * 1024, 1024 ** 2),
    ("1M-4M", 1024 ** 2, 4 * 1024 ** 2),
    ("4M-16M", 4 * 1024 ** 2, 16 * 1024 ** 2),
    ("16M-64M", 16 * 1024 ** 2, 64 * 1024 ** 2),
    ("64M-256M", 64 * 1024 ** 2, 256 * 1024 ** 2),
    ("256M-1G", 256 * 1024 ** 2, 1024 ** 3),
    ("1G-4G", 1024 ** 3, 4 * 1024 ** 3),
    (">=4G", 4 * 1024 ** 3, None),
)


def human(num):
    val = float(num)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if val < 1024 or unit == "PiB":
            if unit == "B":
                return "%d %s" % (int(val), unit)
            return "%.1f %s" % (val, unit)
        val /= 1024.0


def percentile(sorted_vals, p):
    """线性插值分位数: rank=(n-1)*p/100, 与 numpy/statistics inclusive 一致。"""
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return float(sorted_vals[0])
    rank = (n - 1) * (p / 100.0)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return float(sorted_vals[lo])
    return sorted_vals[lo] * (hi - rank) + sorted_vals[hi] * (rank - lo)


def collect_sizes(root):
    sizes = []
    errors = 0
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = os.scandir(current)
        except OSError:
            errors += 1
            continue
        with entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        sizes.append(entry.stat(follow_symlinks=False).st_size)
                except OSError:
                    errors += 1
    return sizes, errors


def histogram(sizes):
    counts = [0] * len(BUCKETS)
    for size in sizes:
        for i, (_label, lo, hi) in enumerate(BUCKETS):
            if size >= lo and (hi is None or size < hi):
                counts[i] += 1
                break
    return counts


def render_histogram(counts, bar_width=40):
    total = sum(counts)
    peak = max(counts) if counts else 0
    lines = ["size histogram (files per magnitude bucket):"]
    for (label, _lo, _hi), count in zip(BUCKETS, counts):
        bar = "#" * int(round(bar_width * count / peak)) if peak else ""
        pct = (100.0 * count / total) if total else 0.0
        lines.append("  %-9s %7d %6.1f%%  %s" % (label, count, pct, bar))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="size-percentile",
        description="计算目录内文件大小的中位数、P90、P99 等分位数, 刻画大小分布形态。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n  python -I size-percentile.py D:\\logs --json")
    parser.add_argument("path", nargs="?", default=".",
                        help="要统计的目录 (默认当前目录)")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 输出(数值单位: 字节)")
    parser.add_argument("--no-hist", action="store_true", help="不显示直方图")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    root = args.path
    if not os.path.isdir(root):
        print("目录不存在: %s" % root, file=sys.stderr)
        return 1

    sizes, errors = collect_sizes(root)
    if not sizes:
        print("目录中没有普通文件: %s" % root, file=sys.stderr)
        return 1

    sizes.sort()
    total = sum(sizes)
    mean = total / len(sizes)
    stats = {}
    for name, p in (("min", 0), ("p10", 10), ("p25", 25), ("p50", 50),
                    ("p75", 75), ("p90", 90), ("p95", 95), ("p99", 99),
                    ("max", 100)):
        stats[name] = percentile(sizes, p)

    if args.json:
        counts = histogram(sizes)
        payload = {
            "dir": os.path.abspath(root),
            "count": len(sizes),
            "total": total,
            "mean": mean,
            "errors": errors,
        }
        payload.update(stats)
        payload["histogram"] = [
            {"label": label, "count": count}
            for (label, _lo, _hi), count in zip(BUCKETS, counts)
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    keys = ("min", "p10", "p25", "p50", "p75", "p90", "p95", "p99", "max")
    print("dir   : %s" % os.path.abspath(root))
    print("files : %d   total: %s   errors: %d" % (len(sizes), human(total), errors))
    print("")
    print("percentiles (linear interpolation, P50 = median):")
    print("  " + "".join("%9s" % k.upper() for k in keys))
    print("  " + "".join("%9s" % human(stats[k]).replace(" ", "") for k in keys))
    print("  mean: %s" % human(mean))
    if not args.no_hist:
        print("")
        print(render_histogram(histogram(sizes)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
