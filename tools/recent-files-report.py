#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recent-files-report.py —— 最近新建/修改文件报告（仅用 Python 标准库）。

列出根目录下最近 N 天内“新建或修改”的文件，按时间倒序；可用 --group dir 按
所在目录分组显示，--top 只看最新前 N 个，--json 输出机器可读结果。

时间口径（--key）：默认 either = max(修改时间 mtime, 创建时间 ctime)，即“新建或
修改”任一发生在窗口内就算命中。Windows 上 ctime 即创建时间；在其他平台上 ctime
是 inode 变更时间。--key mtime 只按修改时间，--key ctime 只按创建时间。
注意：从备份恢复/复制的文件在 Windows 上创建时间是恢复时刻，用 either 口径会命中。

示例命令：
    python recent-files-report.py D:\\work --days 7
    python recent-files-report.py D:\\work --days 3 --group dir
    python recent-files-report.py D:\\work --all-time --top 20
    python recent-files-report.py D:\\work --days 1 --json

退出码：0=成功；2=根目录不存在或不是目录。
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime


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
    ap = argparse.ArgumentParser(description="最近新建/修改文件报告（按时间倒序，可按目录分组）。")
    ap.add_argument("root", help="要扫描的根目录")
    ap.add_argument("--days", type=float, default=7.0, help="时间窗口（天），默认 7")
    ap.add_argument("--key", choices=("either", "mtime", "ctime"), default="either",
                    help="时间口径：either=新建或修改（默认），mtime=仅修改，ctime=仅创建")
    ap.add_argument("--group", choices=("none", "dir"), default="none",
                    help="dir=按所在目录分组显示（组间按组内最新时间倒序）")
    ap.add_argument("--top", type=int, default=0, help="只显示最新前 N 个（0=不限）")
    ap.add_argument("--all-time", action="store_true", help="不限时间，列出全部文件（仍倒序）")
    ap.add_argument("--json", dest="as_json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("错误：根目录不存在或不是目录：%s" % args.root, file=sys.stderr)
        return 2

    now = time.time()
    cutoff = 0.0 if args.all_time else now - max(0.0, args.days) * 86400.0

    scanned = 0
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
            if args.key == "mtime":
                key = st.st_mtime
            elif args.key == "ctime":
                key = st.st_ctime
            else:
                key = max(st.st_mtime, st.st_ctime)
            if key >= cutoff:
                rows.append({"path": os.path.relpath(p, root), "size": st.st_size,
                             "mtime": st.st_mtime, "ctime": st.st_ctime, "key": key})
    rows.sort(key=lambda r: (-r["key"], r["path"].casefold()))
    matched = len(rows)
    total = sum(r["size"] for r in rows)
    shown = rows if args.top <= 0 else rows[:args.top]

    def tstr(ts):
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

    if args.as_json:
        out = {
            "root": root, "days": None if args.all_time else args.days,
            "key": args.key,
            "scanned": scanned, "matched": matched, "total_size": total,
            "shown": len(shown),
            "files": [{"path": r["path"], "size": r["size"], "mtime": r["mtime"],
                       "ctime": r["ctime"], "time": tstr(r["key"])} for r in shown],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    win = "全部时间" if args.all_time else ("%g 天" % args.days)
    kind = {"either": "新建/修改", "mtime": "修改", "ctime": "创建"}[args.key]
    head = "最近%s（%s）：匹配 %d / %d 个文件，合计 %s" % (win, kind, matched, scanned, human(total))
    if args.top > 0 and matched > len(shown):
        head += "（仅显示最新 %d 个）" % len(shown)
    print(head)

    if matched == 0:
        return 0

    def row_line(r):
        return "%s  %9s  %s" % (tstr(r["key"]), human(r["size"]), r["path"])

    if args.group == "dir":
        groups = {}
        for r in shown:
            groups.setdefault(os.path.dirname(r["path"]) or ".", []).append(r)
        ordered = sorted(groups.items(),
                         key=lambda kv: max(x["key"] for x in kv[1]), reverse=True)
        print()
        for drel, items in ordered:
            label = "（根目录）" if drel == "." else drel
            gsize = sum(x["size"] for x in items)
            print("## %s（%d 个文件，%s）" % (label, len(items), human(gsize)))
            for r in items:
                print("   " + row_line(r))
            print()
    else:
        print()
        for r in shown:
            print(row_line(r))

    if errors:
        print("（警告：%d 个条目无法访问，已跳过）" % errors, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
