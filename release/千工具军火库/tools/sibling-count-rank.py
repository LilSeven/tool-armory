#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同级条目排行（sibling-count-rank）。

按“直接子条目数量”对目录树中的目录排行，用于定位把成百上千个文件/子目录
都塞进同一目录的“巨型目录”。默认统计文件 + 子目录两类条目；
--files-only / --dirs-only 只统计其中一类，--min 过滤数量过小的目录，
--top 只显示前 N 名。符号链接目录不递归进入。

用法示例：
    python sibling-count-rank.py K:\\data --top 20
    python sibling-count-rank.py K:\\data --dirs-only --min 5
    python sibling-count-rank.py K:\\data --json

退出码：0 正常完成；2 参数或路径错误。
"""

import argparse
import json
import os
import sys


def scan(root, mode):
    rows = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None,
                                                followlinks=False):
        if mode == "dirs":
            count = len(dirnames)
        elif mode == "files":
            count = len(filenames)
        else:
            count = len(dirnames) + len(filenames)
        rows.append({"dir": dirpath, "count": count})
    return rows


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    parser = argparse.ArgumentParser(
        description="Rank directories by the number of direct child entries "
                    "to spot overloaded 'everything in one folder' directories.")
    parser.add_argument("root", help="directory to scan")
    parser.add_argument("--top", type=int, default=20, metavar="N",
                        help="show at most this many rows (default: 20)")
    parser.add_argument("--min", type=int, default=1, metavar="N",
                        help="only list directories with at least N direct "
                             "entries (default: 1)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--files-only", action="store_true",
                       help="count files only")
    group.add_argument("--dirs-only", action="store_true",
                       help="count subdirectories only")
    parser.add_argument("--json", action="store_true",
                        help="print JSON instead of the human-readable table")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        parser.error("not a directory: %s" % args.root)

    mode = "dirs" if args.dirs_only else ("files" if args.files_only else "both")
    rows = [r for r in scan(root, mode) if r["count"] >= max(args.min, 0)]
    rows.sort(key=lambda r: r["dir"])                 # 先按路径建立稳定次序
    rows.sort(key=lambda r: r["count"], reverse=True)
    total_dirs = len(rows)
    total_entries = sum(r["count"] for r in rows)
    shown = rows[:max(args.top, 0)]

    if args.json:
        print(json.dumps({"root": root, "mode": mode,
                          "directories": total_dirs,
                          "entries_total": total_entries,
                          "ranking": shown},
                         ensure_ascii=False, indent=2))
        return 0

    label = {"both": "files + subdirectories",
             "files": "files only",
             "dirs": "subdirectories only"}[mode]
    print("Sibling entry ranking for: %s" % root)
    print("(counting %s; top %d of %d directories)"
          % (label, len(shown), total_dirs))
    if shown:
        peak = max(r["count"] for r in shown)
        width = 40
        print("")
        print("%4s  %6s  directory" % ("rank", "count"))
        for i, r in enumerate(shown, 1):
            n = max(1, int(round(r["count"] / float(peak) * width))) if r["count"] else 0
            print("%4d  %6d  |%-40s %s" % (i, r["count"], "#" * n, r["dir"]))
    else:
        print("No directory matches the given --min threshold.")
    print("")
    print("Scanned %d directories, %d direct entries in total."
          % (total_dirs, total_entries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
