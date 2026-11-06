#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""目录文件数普查 (file-count-census)

递归统计每个目录的文件数与子目录数，找出文件数量异常膨胀的目录。

统计口径:
    直接文件数 / 直接子目录数 = 目录的直接子项
    递归文件数 / 递归大小     = 该目录整个子树的合计

膨胀判定: 目录"直接文件数" >= max(--min-files, 均值+2*标准差)。

用法:
    python file-count-census.py <目录>
    python file-count-census.py <目录> --min-files 100 --top 20
    python file-count-census.py <目录> --json

示例:
    python file-count-census.py D:/logs --min-files 500
"""
import argparse
import json
import math
import os
import sys
import unicodedata


def human(n) -> str:
    """字节数 -> 人类可读字符串。"""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if n < 1024 or unit == "PB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024.0
    return f"{n:,.1f} PB"


def dwidth(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def pad(s: str, width: int) -> str:
    return s + " " * max(0, width - dwidth(s))


def lpad(s: str, width: int) -> str:
    return " " * max(0, width - dwidth(s)) + s


def _ignore_error(_exc):
    """os.walk 的 onerror 钩子: 无权限的子树直接跳过。"""
    pass


def scan(root: str):
    """遍历 root, 返回 {目录路径: {"files","dirs","rec_files","rec_bytes"}}。"""
    stats = {}
    for dirpath, dirnames, filenames in os.walk(root, onerror=_ignore_error):
        rec_bytes = 0
        for name in filenames:
            try:
                rec_bytes += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
        stats[os.path.normpath(dirpath)] = {
            "files": len(filenames),      # 直接文件数
            "dirs": len(dirnames),        # 直接子目录数
            "rec_files": len(filenames),  # 递归文件总数(下面自底向上累加)
            "rec_bytes": rec_bytes,       # 递归总字节
        }
    # 自底向上把子目录的递归值并入父目录(按路径分隔符数量从深到浅)
    for path in sorted(stats, key=lambda p: -p.count(os.sep)):
        parent = os.path.dirname(path)
        if parent != path and parent in stats:
            stats[parent]["rec_files"] += stats[path]["rec_files"]
            stats[parent]["rec_bytes"] += stats[path]["rec_bytes"]
    return stats


def bloated(stats, min_files: int, top: int):
    """返回 (膨胀目录列表, 阈值, 均值, 标准差)。"""
    counts = [s["files"] for s in stats.values()]
    if not counts:
        return [], 0, 0.0, 0.0
    mean = sum(counts) / len(counts)
    std = math.sqrt(sum((x - mean) ** 2 for x in counts) / len(counts))
    threshold = max(min_files, math.ceil(mean + 2 * std))
    hits = sorted(((p, s) for p, s in stats.items() if s["files"] >= threshold),
                  key=lambda kv: (-kv[1]["files"], kv[0]))
    return hits[:top], threshold, mean, std


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="file-count-census",
        description="递归统计每个目录的文件数与子目录数, 找出文件数异常膨胀的目录")
    ap.add_argument("root", help="要普查的根目录")
    ap.add_argument("--min-files", type=int, default=0, metavar="N",
                    help="膨胀阈值下限(默认 0, 即用 均值+2*标准差 自动判定)")
    ap.add_argument("--top", type=int, default=15, metavar="N",
                    help="最多列出 N 个膨胀目录(默认 15)")
    ap.add_argument("--json", action="store_true", help="输出 JSON(含全部目录统计)")
    args = ap.parse_args(argv)

    root = os.path.normpath(os.path.abspath(args.root))
    if not os.path.isdir(root):
        print(f"错误: 不是目录: {root}", file=sys.stderr)
        return 2

    stats = scan(root)
    hits, threshold, mean, std = bloated(stats, args.min_files, args.top)
    total_dirs = len(stats)
    total_files = stats[root]["rec_files"] if root in stats else \
        sum(s["rec_files"] for s in stats.values())

    if args.json:
        print(json.dumps({
            "root": root, "dirs": total_dirs, "files": total_files,
            "threshold": threshold,
            "mean_direct_files": round(mean, 2),
            "std_direct_files": round(std, 2),
            "bloated": [dict(path=p, **s) for p, s in hits],
            "all": stats,
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"普查根目录: {root}")
    print(f"目录总数: {total_dirs:,}    文件总数: {total_files:,}")
    print(f"膨胀阈值(直接文件数) >= {threshold:,}    "
          f"(均值 {mean:.1f} + 2x标准差 {std:.1f}, 下限 {args.min_files})")
    if hits:
        print(f"\n异常膨胀目录 {len(hits)} 个:")
        pw = max([dwidth(p) for p, _ in hits] + [dwidth("路径")])
        header = (pad("路径", pw) + "  " + lpad("直接文件", 8) + "  "
                  + lpad("直接子目录", 10) + "  " + lpad("递归文件", 8) + "  "
                  + lpad("递归大小", 10))
        print(header)
        print("-" * dwidth(header))
        for p, s in hits:
            print(f"{pad(p, pw)}  {s['files']:>8,}  {s['dirs']:>10,}"
                  f"  {s['rec_files']:>8,}  {human(s['rec_bytes']):>10}")
    else:
        print("\n未发现直接文件数超过阈值的目录。")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
