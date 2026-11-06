#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stale-file-finder.py —— 陈旧文件查找器：找出多年未修改的大文件，输出归档候选清单与预估可归档空间（仅标准库，只读）。

扫描目录树，筛选“最后修改时间早于 --days 天 且 大小不小于 --min-size”的文件，
按大小降序输出归档候选清单；并汇总候选数量、预估可归档空间（候选合计大小）及
其占扫描总大小的比例。本工具只读：不做任何移动、删除或归档操作。

大小参数可用 123、10KB、1.5MB、2GB 等写法（KB/MB/GB/TB 按 1024 进制解释）。

示例命令：
    python stale-file-finder.py D:\\data --days 730 --min-size 100MB
    python stale-file-finder.py D:\\data --min-size 1GB --top 20
    python stale-file-finder.py D:\\data --days 365 --min-size 10MB --json

退出码：0=成功；2=根目录不存在/不是目录，或大小参数不合法。
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

UNITS = {"": 1, "b": 1,
         "k": 1024, "kb": 1024, "kib": 1024,
         "m": 1024 ** 2, "mb": 1024 ** 2, "mib": 1024 ** 2,
         "g": 1024 ** 3, "gb": 1024 ** 3, "gib": 1024 ** 3,
         "t": 1024 ** 4, "tb": 1024 ** 4, "tib": 1024 ** 4}


def parse_size(text):
    s = str(text).strip().lower().replace(" ", "").replace("_", "")
    num, unit = s, ""
    for i, ch in enumerate(s):
        if ch.isalpha():
            num, unit = s[:i], s[i:]
            break
    try:
        val = float(num)
    except ValueError:
        raise argparse.ArgumentTypeError("大小不合法：%r" % text)
    if val < 0 or unit not in UNITS:
        raise argparse.ArgumentTypeError("大小不合法：%r" % text)
    return int(val * UNITS[unit])


def human(n):
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    x = float(n)
    i = 0
    while x >= 1024.0 and i < len(units) - 1:
        x /= 1024.0
        i += 1
    return ("%d %s" % (round(x), units[i])) if i == 0 else ("%.2f %s" % (x, units[i]))


def _reconfigure_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main():
    _reconfigure_stdio()
    ap = argparse.ArgumentParser(
        description="陈旧文件查找器：多年未修改的大文件归档候选清单与预估可归档空间（只读）。")
    ap.add_argument("root", help="要扫描的根目录")
    ap.add_argument("--days", type=float, default=365.0,
                    help="未修改天数阈值（mtime 早于该天数视为陈旧），默认 365")
    ap.add_argument("--min-size", type=parse_size, default=1048576,
                    metavar="SIZE", help="单文件大小下限，如 100MB（默认 1MB）")
    ap.add_argument("--top", type=int, default=0, help="只显示最大的前 N 个（0=不限）")
    ap.add_argument("--json", dest="as_json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("错误：根目录不存在或不是目录：%s" % args.root, file=sys.stderr)
        return 2

    now = time.time()
    cutoff = now - max(0.0, args.days) * 86400.0

    scanned = 0
    total_scanned = 0
    errors = 0
    rows = []

    def on_error(_e):
        nonlocal errors
        errors += 1

    for dirpath, _dirs, filenames in os.walk(root, onerror=on_error, followlinks=False):
        for name in filenames:
            p = os.path.join(dirpath, name)
            try:
                st = os.lstat(p)
            except OSError:
                errors += 1
                continue
            scanned += 1
            total_scanned += st.st_size
            if st.st_mtime <= cutoff and st.st_size >= args.min_size:
                rows.append({"path": os.path.relpath(p, root), "size": st.st_size,
                             "mtime": st.st_mtime})
    rows.sort(key=lambda r: (-r["size"], r["path"].casefold()))
    shown = rows if args.top <= 0 else rows[:args.top]
    cand_size = sum(r["size"] for r in rows)
    pct = (cand_size / total_scanned * 100.0) if total_scanned else 0.0

    if args.as_json:
        out = {
            "root": root, "days": args.days, "min_size": args.min_size,
            "scanned": scanned, "total_size": total_scanned,
            "candidates": len(rows), "archivable_size": cand_size,
            "archivable_pct": round(pct, 1),
            "files": [{"path": r["path"], "size": r["size"], "mtime": r["mtime"],
                       "age_days": int((now - r["mtime"]) // 86400),
                       "age_years": round((now - r["mtime"]) / 31536000.0, 2),
                       "date": datetime.fromtimestamp(r["mtime"]).strftime("%Y-%m-%d")}
                      for r in shown],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    print("筛选：mtime 早于 %s（%.0f 天前）且 单文件 ≥ %s（只读报告，未做任何移动/删除）"
          % (datetime.fromtimestamp(cutoff).strftime("%Y-%m-%d"), args.days, human(args.min_size)))
    if not rows:
        print("没有满足阈值的文件（扫描 %d 个文件，共 %s）。" % (scanned, human(total_scanned)))
    else:
        print()
        for r in shown:
            age_days = int((now - r["mtime"]) // 86400)
            years = (now - r["mtime"]) / 31536000.0
            date = datetime.fromtimestamp(r["mtime"]).strftime("%Y-%m-%d")
            print("%9s  %s（%d 天前 ≈ %.1f 年未动）  %s"
                  % (human(r["size"]), date, age_days, years, r["path"]))
        print()
        print("扫描 %d 个文件（%s）；归档候选 %d 个，预估可归档空间 %s（占扫描总量 %.1f%%）。"
              % (scanned, human(total_scanned), len(rows), human(cand_size), pct))
    if errors:
        print("（警告：%d 个条目无法访问，已跳过）" % errors, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
