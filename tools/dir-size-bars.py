#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dir-size-bars.py —— 用 ASCII 条形图展示各子目录磁盘占用占比（仅用 Python 标准库）。

统计目标目录下每个一级子目录（以及根目录直属文件合计）的递归大小，
按比例绘制 '#' 条形图（条长相对最大者缩放），一眼看出空间大头。

示例命令：
    python dir-size-bars.py D:\\projects
    python dir-size-bars.py D:\\projects --width 60 --sort name
    python dir-size-bars.py D:\\projects --si --unit M

退出码：0=成功；1=目录不存在或有条目无法访问。
"""

import argparse
import os
import sys


def human(n, si=False, unit=None):
    units = ("B", "kB", "MB", "GB", "TB", "PB") if si else ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    base = 1000.0 if si else 1024.0
    if unit and unit != "auto":
        i = {"B": 0, "K": 1, "M": 2, "G": 3, "T": 4, "P": 5}[unit.upper()]
        x = n / base ** i
    else:
        x = float(n)
        i = 0
        while x >= base and i < len(units) - 1:
            x /= base
            i += 1
    return ("%d %s" % (round(x), units[i])) if i == 0 else ("%.1f %s" % (x, units[i]))


def scan_tree(root):
    """返回 (agg, nfiles, errors)。agg[目录绝对路径] = 该目录累计大小（含子孙）。"""
    direct = {}
    errors = []
    nfiles = 0

    def on_error(err):
        errors.append(str(err))

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error,
                                                followlinks=False):
        dirnames[:] = [d for d in dirnames
                       if not os.path.islink(os.path.join(dirpath, d))]
        subtotal = 0
        for name in filenames:
            p = os.path.join(dirpath, name)
            try:
                subtotal += os.lstat(p).st_size
                nfiles += 1
            except OSError as e:
                errors.append(str(e))
        direct[dirpath] = subtotal
    agg = dict(direct)
    for d in sorted(direct, key=lambda p: (p.count(os.sep), len(p)), reverse=True):
        parent = os.path.dirname(d)
        if parent != d and parent in agg:
            agg[parent] += agg[d]
    return agg, nfiles, errors


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        prog="dir-size-bars",
        description="ASCII bar chart of relative disk usage per immediate "
                    "subdirectory, to spot the space hogs at a glance.")
    ap.add_argument("dir", help="directory whose children to chart")
    ap.add_argument("-w", "--width", type=int, default=40, metavar="N",
                    help="max bar length in characters (default 40)")
    ap.add_argument("--sort", choices=("size", "name"), default="size",
                    help="sort rows by size (default) or by name")
    ap.add_argument("--unit", choices=("auto", "B", "K", "M", "G", "T"), default="auto",
                    help="force a unit instead of auto-scaling")
    ap.add_argument("--si", action="store_true", help="use 1000-based units (kB/MB)")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.dir)
    if not os.path.isdir(root):
        print("error: not a directory: %s" % root, file=sys.stderr)
        return 1
    agg, nfiles, errors = scan_tree(root)

    rows = []
    direct_files = 0
    for name in os.listdir(root):
        p = os.path.join(root, name)
        if os.path.isdir(p) and not os.path.islink(p):
            rows.append((name, agg.get(p, 0)))
        else:
            try:
                direct_files += os.lstat(p).st_size
            except OSError as e:
                errors.append(str(e))
    if direct_files:
        rows.append(("(direct files)", direct_files))

    if not rows:
        print("(empty directory: %s)" % root)
        for e in errors:
            print("warning: %s" % e, file=sys.stderr)
        return 1 if errors else 0

    if args.sort == "size":
        rows.sort(key=lambda t: (-t[1], t[0]))
    else:
        rows.sort(key=lambda t: t[0].lower())
    total = sum(s for _, s in rows)
    maxv = max(s for _, s in rows)
    width = max(5, args.width)
    name_w = min(28, max(len(n) for n, _ in rows))
    total_str = "(nothing measured)" if total == 0 else human(total, args.si, args.unit)
    print("disk usage of %s (total %s):" % (root, total_str))
    for name, size in rows:
        disp = name if len(name) <= name_w else name[:name_w - 3] + "..."
        bar_len = int(round(width * size / maxv)) if maxv else 0
        pct = (size * 100.0 / total) if total else 0.0
        print("%-*s |%-*s| %9s  %5.1f%%"
              % (name_w, disp, width, "#" * bar_len,
                 human(size, args.si, args.unit), pct))
    for e in errors:
        print("warning: %s" % e, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
