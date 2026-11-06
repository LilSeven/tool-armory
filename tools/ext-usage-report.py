#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扩展名占用分析 (ext-usage-report)

按扩展名汇总目录下文件的数量与总大小并计算占比，识别哪类文件占据空间。
说明: 扩展名取 os.path.splitext 的最后一段并转小写, 如 x.tar.gz 计为 gz;
     无扩展名文件归入 "(无扩展名)"。

用法:
    python ext-usage-report.py <目录>
    python ext-usage-report.py <目录> --top 15
    python ext-usage-report.py <目录> --all
    python ext-usage-report.py <目录> --json

示例:
    python ext-usage-report.py D:/projects --top 15
"""
import argparse
import json
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


def collect(root: str):
    """遍历 root, 返回 ({ext: [count, bytes]}, 文件总数)。"""
    groups = {}
    nfiles = 0
    for dirpath, _dirs, names in os.walk(root, onerror=lambda e: None):
        for name in names:
            try:
                size = os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                continue
            ext = os.path.splitext(name)[1].lower().lstrip(".") or "(无扩展名)"
            g = groups.setdefault(ext, [0, 0])
            g[0] += 1
            g[1] += size
            nfiles += 1
    return groups, nfiles


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="ext-usage-report",
        description="按扩展名汇总文件数量与总大小并计算占比, 识别哪类文件占据空间")
    ap.add_argument("root", help="要分析的根目录")
    ap.add_argument("--top", type=int, default=20, metavar="N",
                    help="默认最多列出 N 类扩展名(默认 20)")
    ap.add_argument("--all", action="store_true",
                    help="列出全部扩展名(忽略 --top)")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"错误: 不是目录: {root}", file=sys.stderr)
        return 2

    groups, nfiles = collect(root)
    total_bytes = sum(v[1] for v in groups.values())
    rows = sorted(
        ({"ext": ext, "count": cnt, "bytes": sz,
          "count_pct": round(cnt / nfiles * 100, 1) if nfiles else 0.0,
          "bytes_pct": round(sz / total_bytes * 100, 1) if total_bytes else 0.0}
         for ext, (cnt, sz) in groups.items()),
        key=lambda r: (-r["bytes"], -r["count"], r["ext"]))

    if args.json:
        print(json.dumps({"root": root, "files": nfiles,
                          "total_bytes": total_bytes, "extensions": rows},
                         ensure_ascii=False, indent=2))
        return 0

    if not rows:
        print("(目录为空, 未找到任何文件)")
        return 0

    shown = rows if args.all else rows[:args.top]
    ew = max([dwidth(r["ext"]) for r in shown] + [dwidth("扩展名")])
    print(f"目录: {root}")
    print(f"文件总数: {nfiles:,}    总大小: {human(total_bytes)}    扩展名种类: {len(rows)}")
    print()
    header = (pad("扩展名", ew) + "  " + lpad("文件数", 8) + "  "
              + lpad("数量占比", 9) + "  " + lpad("总大小", 10) + "  "
              + lpad("大小占比", 9))
    print(header)
    print("-" * dwidth(header))
    for r in shown:
        print(f"{pad(r['ext'], ew)}  {r['count']:>8,}  {r['count_pct']:>8.1f}%"
              f"  {human(r['bytes']):>10}  {r['bytes_pct']:>8.1f}%")
    if not args.all and len(rows) > len(shown):
        rest = rows[len(shown):]
        print(f"(其余 {len(rest)} 类: "
              f"{sum(r['count'] for r in rest):,} 个文件, "
              f"{human(sum(r['bytes'] for r in rest))})")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
