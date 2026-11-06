#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""磁盘剩余空间报告 (disk-free-report)

用 shutil.disk_usage 列出各盘符/挂载点的总容量、已用、剩余空间与使用率。

用法:
    python disk-free-report.py                  # Windows: 扫描所有存在的盘符; POSIX: 解析 /proc/mounts
    python disk-free-report.py C:/ D:/          # 只检查指定路径(盘符或任意目录所在卷)
    python disk-free-report.py --json           # 输出机器可读 JSON
    python disk-free-report.py --min-free-gb 10 # 只列出剩余空间不足 10 GiB 的卷

示例:
    python disk-free-report.py
    python disk-free-report.py --json K:/
"""
import argparse
import json
import os
import shutil
import string
import sys
import unicodedata


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
    """终端显示宽度(中日韩全角字符按 2 列计)。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def pad(s: str, width: int) -> str:
    """左对齐并按显示宽度补空格。"""
    return s + " " * max(0, width - dwidth(s))


def lpad(s: str, width: int) -> str:
    """右对齐并按显示宽度补空格。"""
    return " " * max(0, width - dwidth(s)) + s


def default_targets():
    """缺省要检查的卷: Windows 扫描 A-Z 盘符; POSIX 解析 /proc/mounts。"""
    if os.name == "nt":
        return [f"{L}:\\" for L in string.ascii_uppercase
                if os.path.exists(f"{L}:\\")]
    mounts = []
    try:  # POSIX 分支, 仅在类 Unix 系统执行
        with open("/proc/mounts", "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[1].startswith("/"):
                    mp = parts[1]
                    if any(mp.startswith(p) for p in ("/proc", "/sys", "/dev", "/run", "/snap")):
                        continue
                    if mp not in mounts:
                        mounts.append(mp)
    except OSError:
        pass
    return mounts or ["/"]


def probe(path: str):
    """探测单个路径所在卷, 返回 (信息dict, None) 或 (None, 错误信息)。"""
    try:
        u = shutil.disk_usage(path)
    except (OSError, ValueError) as exc:
        return None, str(exc)
    pct = (u.used / u.total * 100.0) if u.total else 0.0
    return {
        "path": path,
        "total": u.total,
        "used": u.used,
        "free": u.free,
        "percent": round(pct, 1),
    }, None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="disk-free-report",
        description="用 shutil.disk_usage 列出各盘符/挂载点的总容量、已用、剩余与使用率")
    ap.add_argument("paths", nargs="*",
                    help="要检查的路径(盘符或目录); 缺省时自动扫描全部盘符/挂载点")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--min-free-gb", type=float, default=None, metavar="N",
                    help="只列出剩余空间不足 N GiB 的卷")
    args = ap.parse_args(argv)

    targets = [os.path.abspath(p) for p in args.paths] or default_targets()
    rows, errors = [], []
    for t in targets:
        info, err = probe(t)
        if info is None:
            errors.append({"path": t, "error": err})
        elif args.min_free_gb is not None and info["free"] >= args.min_free_gb * 1024 ** 3:
            continue  # 剩余充足, 被 --min-free-gb 过滤
        else:
            rows.append(info)

    rows.sort(key=lambda r: -r["percent"])

    if args.json:
        print(json.dumps({"volumes": rows, "errors": errors},
                         ensure_ascii=False, indent=2))
        return 0

    if rows:
        label = "路径/挂载点"
        w = max([dwidth(r["path"]) for r in rows] + [dwidth(label)])
        header = (pad(label, w) + "  " + lpad("总容量", 10) + "  " + lpad("已用", 10)
                  + "  " + lpad("剩余", 10) + "  " + lpad("使用率", 8))
        print(header)
        print("-" * dwidth(header))
        for r in rows:
            print(f"{pad(r['path'], w)}  {human(r['total']):>10}  {human(r['used']):>10}"
                  f"  {human(r['free']):>10}  {r['percent']:>7.1f}%")
    else:
        print("(没有符合条件的卷)")

    for e in errors:
        print(f"[跳过] {e['path']}: {e['error']}", file=sys.stderr)
    if not rows and not errors:
        print("未找到任何盘符/挂载点", file=sys.stderr)
        return 1
    if not rows and args.paths:
        print("指定的路径全部不可用", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
