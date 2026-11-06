#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""目录增长追踪器（file-count-history）。

每次运行统计目录的文件数与总大小，把一行记录 (时间戳, 文件数, 总字节) 追加
到 CSV 日志（默认 <目录>/.file_count_history.csv，日志文件自身不计入统计），
然后打印本次数值、与上一次运行的差值，以及最近若干条记录的字节量趋势条形图。

CSV 每行三列：ISO 时间戳, 文件数, 总字节数（UTF-8、无表头），可直接用
Excel / pandas 查看。

用法示例：
    python file-count-history.py K:\\proj
    python file-count-history.py K:\\proj --log K:\\logs\\proj.csv --last 20
    python file-count-history.py K:\\proj --json

退出码：0 正常完成；2 参数或路径错误。
"""

import argparse
import csv
import json
import os
import stat
import sys
from datetime import datetime

LOG_NAME = ".file_count_history.csv"


def human_size(n):
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if size < 1024 or unit == "PB":
            return "%d B" % int(size) if unit == "B" else "%.1f %s" % (size, unit)
        size /= 1024.0


def measure(root, skip):
    """统计文件数与总大小；skip 为需排除的规范化绝对路径（日志自身）。"""
    files = total = 0
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None,
                                                followlinks=False):
        for name in filenames:
            path = os.path.abspath(os.path.join(dirpath, name))
            if os.path.normcase(path) == skip:
                continue
            try:
                st = os.stat(path, follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISLNK(st.st_mode):
                continue
            files += 1
            total += st.st_size
    return files, total


def read_log(path):
    records = []
    if not os.path.isfile(path):
        return records
    with open(path, "r", encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh):
            if not row or len(row) < 3:
                continue
            try:
                records.append({"ts": row[0], "files": int(row[1]),
                                "bytes": int(row[2])})
            except ValueError:
                print("warning: skip malformed log line: %r" % (row,),
                      file=sys.stderr)
    return records


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    parser = argparse.ArgumentParser(
        description="Track directory growth: append file count and total size "
                    "to a CSV log, then show the trend.")
    parser.add_argument("root", help="directory to measure")
    parser.add_argument("--log", metavar="PATH",
                        help="history CSV path (default: <root>/%s)" % LOG_NAME)
    parser.add_argument("--last", type=int, default=10, metavar="N",
                        help="records shown in the trend chart (default: 10)")
    parser.add_argument("--json", action="store_true",
                        help="print JSON instead of the human-readable report")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        parser.error("not a directory: %s" % args.root)
    log_path = os.path.abspath(args.log) if args.log else os.path.join(root, LOG_NAME)
    skip = os.path.normcase(log_path)

    files, total = measure(root, skip)
    now = datetime.now().isoformat(timespec="seconds")
    history = read_log(log_path)
    with open(log_path, "a", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerow([now, files, total])
    history.append({"ts": now, "files": files, "bytes": total})

    prev = history[-2] if len(history) >= 2 else None
    d_files = d_bytes = 0
    if prev:
        d_files = files - prev["files"]
        d_bytes = total - prev["bytes"]
    d0_files = files - history[0]["files"]
    d0_bytes = total - history[0]["bytes"]

    if args.json:
        print(json.dumps({
            "root": root, "log": log_path,
            "current": {"ts": now, "files": files, "bytes": total},
            "runs_recorded": len(history),
            "previous": prev,
            "delta_since_previous": ({"files": d_files, "bytes": d_bytes}
                                     if prev else None),
            "delta_since_first": {"files": d0_files, "bytes": d0_bytes},
            "history_tail": history[-max(args.last, 0):],
        }, ensure_ascii=False, indent=2))
        return 0

    print("Directory : %s" % root)
    print("Log       : %s" % log_path)
    print("Run #%d at %s : files=%d, bytes=%d (%s)"
          % (len(history), now, files, total, human_size(total)))
    if prev:
        print("Previous run at %s : files=%d, bytes=%d"
              % (prev["ts"], prev["files"], prev["bytes"]))
        print("Delta since previous : files %+d, bytes %+d (%s)"
              % (d_files, d_bytes, human_size(abs(d_bytes))))
    else:
        print("Baseline recorded (first run for this log).")
    if len(history) > 1:
        print("Delta since first run: files %+d, bytes %+d across %d recorded runs."
              % (d0_files, d0_bytes, len(history)))

    shown = history[-max(args.last, 0):]
    if len(shown) >= 2:
        peak = max(r["bytes"] for r in shown) or 1
        width = 40
        print("")
        print("Trend of the last %d runs (bytes):" % len(shown))
        for r in shown:
            n = max(1, int(round(r["bytes"] / float(peak) * width))) if r["bytes"] else 0
            print("  %19s  %8d  |%s" % (r["ts"], r["bytes"], "#" * n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
