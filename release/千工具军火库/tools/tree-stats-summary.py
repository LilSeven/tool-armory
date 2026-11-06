#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tree-stats-summary.py —— 目录树速览摘要：一行输出总大小、文件数、目录数、最大文件、平均深度等速览指标（仅用 Python 标准库）。

对给定目录做一次递归扫描，在一行内给出速览指标：总大小、文件数、目录数（含空
目录数）、最大文件及其大小、文件平均相对深度、最大深度、无法访问条目数、耗时。
--json 可输出机器可读结果。

说明：
  * 大小为名义大小 st_size（apparent size），不跟随符号链接；
  * “深度”是相对根目录的层级：根目录直下的文件为 0，子目录里的文件为 1，依此类推。

示例命令：
    python tree-stats-summary.py D:\\projects
    python tree-stats-summary.py D:\\projects --si          # 1000 进制单位（kB/MB）
    python tree-stats-summary.py D:\\projects --json        # 机器可读输出

退出码：0=成功；1=扫描中有无法访问的条目（统计仍会输出）；2=根目录不存在或不是目录。
"""

import argparse
import json
import os
import sys
import time


def human(n, si=False):
    units = ("B", "kB", "MB", "GB", "TB", "PB") if si else ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    base = 1000.0 if si else 1024.0
    x = float(n)
    i = 0
    while x >= base and i < len(units) - 1:
        x /= base
        i += 1
    return ("%d %s" % (round(x), units[i])) if i == 0 else ("%.2f %s" % (x, units[i]))


def _reconfigure_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def collect(root):
    stats = {"total_size": 0, "files": 0, "dirs": 0, "empty_dirs": 0, "errors": 0,
             "largest_size": -1, "largest_rel": "", "depth_sum": 0, "max_depth": 0}

    def on_error(_err):
        stats["errors"] += 1

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error, followlinks=False):
        rel = os.path.relpath(dirpath, root)
        if rel == ".":
            dir_depth = 0
        else:
            stats["dirs"] += 1
            dir_depth = rel.count(os.sep) + 1
            if not dirnames and not filenames:
                stats["empty_dirs"] += 1
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                st = os.lstat(path)
            except OSError:
                stats["errors"] += 1
                continue
            stats["total_size"] += st.st_size
            stats["files"] += 1
            stats["depth_sum"] += dir_depth
            if dir_depth > stats["max_depth"]:
                stats["max_depth"] = dir_depth
            if st.st_size > stats["largest_size"]:
                stats["largest_size"] = st.st_size
                stats["largest_rel"] = os.path.relpath(path, root)
    return stats


def main():
    _reconfigure_stdio()
    ap = argparse.ArgumentParser(
        description="目录树速览摘要：一行输出总大小、文件数、目录数、最大文件、平均深度等指标。")
    ap.add_argument("root", help="要统计的根目录")
    ap.add_argument("--si", action="store_true",
                    help="用 1000 进制单位（kB/MB）而非 1024 进制（KiB/MiB）")
    ap.add_argument("--json", dest="as_json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("错误：根目录不存在或不是目录：%s" % args.root, file=sys.stderr)
        return 2

    t0 = time.perf_counter()
    s = collect(root)
    elapsed = time.perf_counter() - t0

    files = s["files"]
    avg_depth = (s["depth_sum"] / files) if files else 0.0
    largest_txt = ("%s（%s）" % (s["largest_rel"], human(s["largest_size"], args.si))) if files else "（无文件）"

    result = {
        "root": root,
        "total_size": s["total_size"],
        "total_size_human": human(s["total_size"], args.si),
        "files": files,
        "dirs": s["dirs"],
        "empty_dirs": s["empty_dirs"],
        "largest_file": s["largest_rel"] if files else None,
        "largest_size": s["largest_size"] if files else 0,
        "avg_depth": round(avg_depth, 2),
        "max_depth": s["max_depth"],
        "unreadable": s["errors"],
        "elapsed_sec": round(elapsed, 3),
    }

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("%s: 总大小 %s | 文件 %d | 目录 %d（空 %d） | 最大文件 %s | 平均深度 %.2f | 最大深度 %d | 无法访问 %d | 耗时 %.2fs"
              % (root, result["total_size_human"], files, s["dirs"], s["empty_dirs"],
                 largest_txt, avg_depth, s["max_depth"], s["errors"], elapsed))

    return 1 if s["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
