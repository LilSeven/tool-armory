#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""隐藏文件报告（hidden-file-report）。

统计目录树中各目录的隐藏文件数量与占用空间。隐藏文件判定（满足其一即可）：
  1. 文件名以 "." 开头（跨平台约定）；
  2. Windows 上带有系统隐藏属性 FILE_ATTRIBUTE_HIDDEN。

只统计普通文件（隐藏目录本身不计入数量，但会递归进入隐藏目录继续统计），
符号链接跳过。

用法示例：
    python hidden-file-report.py K:\\data
    python hidden-file-report.py K:\\data --sort size --top 50
    python hidden-file-report.py K:\\data --min-bytes 1024
    python hidden-file-report.py K:\\data --json

退出码：0 正常完成；2 参数或路径错误。
"""

import argparse
import json
import os
import stat
import sys

FILE_ATTRIBUTE_HIDDEN = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0x2)


def human_size(n):
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if size < 1024 or unit == "PB":
            return "%d B" % int(size) if unit == "B" else "%.1f %s" % (size, unit)
        size /= 1024.0


def is_hidden_file(name, st):
    if name.startswith("."):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_HIDDEN)


def scan(root):
    """遍历目录树，返回 (每目录统计列表, 汇总)。"""
    rows = []
    totals = {"dirs": 0, "files": 0, "hidden": 0, "hidden_bytes": 0}
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None,
                                                followlinks=False):
        files = hidden = hbytes = 0
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                st = os.stat(path, follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISLNK(st.st_mode):
                continue
            files += 1
            if is_hidden_file(name, st):
                hidden += 1
                hbytes += st.st_size
        totals["dirs"] += 1
        totals["files"] += files
        totals["hidden"] += hidden
        totals["hidden_bytes"] += hbytes
        rows.append({"dir": dirpath, "files": files, "hidden": hidden,
                     "hidden_bytes": hbytes})
    return rows, totals


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    parser = argparse.ArgumentParser(
        description="Hidden file report: count and size of hidden files per directory.")
    parser.add_argument("root", help="directory to scan")
    parser.add_argument("--sort", choices=("count", "size"), default="count",
                        help="sort the listing by hidden count or hidden size (default: count)")
    parser.add_argument("--top", type=int, default=20, metavar="N",
                        help="show at most this many rows (default: 20)")
    parser.add_argument("--min-bytes", type=int, default=0, metavar="N",
                        help="only list directories whose hidden bytes >= N")
    parser.add_argument("--all", action="store_true",
                        help="also list directories that have no hidden files")
    parser.add_argument("--json", action="store_true",
                        help="print JSON instead of the human-readable table")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        parser.error("not a directory: %s" % args.root)

    rows, totals = scan(root)

    if args.min_bytes > 0:
        shown = [r for r in rows if r["hidden_bytes"] >= args.min_bytes]
    elif args.all:
        shown = list(rows)
    else:
        shown = [r for r in rows if r["hidden"] > 0]

    primary = (lambda r: (r["hidden"], r["hidden_bytes"])) if args.sort == "count" \
        else (lambda r: (r["hidden_bytes"], r["hidden"]))
    shown.sort(key=lambda r: r["dir"])          # 先按路径建立稳定次序
    shown.sort(key=primary, reverse=True)
    shown = shown[:max(args.top, 0)]

    if args.json:
        print(json.dumps({"root": root, "totals": totals, "directories": shown},
                         ensure_ascii=False, indent=2))
        return 0

    print("Hidden file report for: %s" % root)
    print("Scanned %d directories, %d files in total."
          % (totals["dirs"], totals["files"]))
    if not shown:
        print("No hidden files found.")
    else:
        print("")
        print("Directories with hidden files (top %d, sorted by %s):"
              % (len(shown), args.sort))
        print("%7s  %10s  %6s  directory" % ("hidden", "size", "files"))
        for r in shown:
            print("%7d  %10s  %6d  %s"
                  % (r["hidden"], human_size(r["hidden_bytes"]), r["files"], r["dir"]))
    print("")
    print("Total: %d hidden files, %s in hidden files."
          % (totals["hidden"], human_size(totals["hidden_bytes"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
