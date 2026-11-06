#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dirtree-du.py —— 仿 du 的目录树磁盘占用统计器（仅用 Python 标准库）。

递归统计目录树下每个子目录的累计大小（含其全部子孙文件），按大小降序
输出人类可读单位的结果，最后给出总计。
说明：使用文件名义大小（st_size，即 apparent size），不跟随符号链接/联接点。

示例命令：
    python dirtree-du.py D:\\downloads
    python dirtree-du.py D:\\downloads --max-depth 1     # 只看第一层子目录
    python dirtree-du.py D:\\downloads --sort name --unit K
    python dirtree-du.py D:\\downloads --si --raw        # 1000 进制 + 原始字节数

退出码：0=成功；1=目录不存在或有条目无法访问（警告输出到 stderr）。
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
    # 自底向上聚合：按路径分隔符数量从深到浅
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
        prog="dirtree-du",
        description="du-like recursive disk usage: totals for every subdirectory "
                    "of a tree, sorted by size, human-readable units.")
    ap.add_argument("dir", help="directory tree to measure")
    ap.add_argument("-d", "--max-depth", type=int, default=0, metavar="N",
                    help="only list subdirectories up to depth N (0 = all)")
    ap.add_argument("--sort", choices=("size", "name"), default="size",
                    help="sort output by size (default) or by name")
    ap.add_argument("--unit", choices=("auto", "B", "K", "M", "G", "T"), default="auto",
                    help="force a unit instead of auto-scaling")
    ap.add_argument("--si", action="store_true", help="use 1000-based units (kB/MB)")
    ap.add_argument("--raw", action="store_true", help="also show raw byte counts")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.dir)
    if not os.path.isdir(root):
        print("error: not a directory: %s" % root, file=sys.stderr)
        return 1
    agg, nfiles, errors = scan_tree(root)

    rows = []
    for d, total in agg.items():
        if d == root:
            continue
        rel = os.path.relpath(d, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if args.max_depth and depth > args.max_depth:
            continue
        rows.append((total, d))
    if args.sort == "size":
        rows.sort(key=lambda t: (-t[0], t[1]))
    else:
        rows.sort(key=lambda t: t[1].lower())

    size_strs = []
    for total, _d in rows:
        s = human(total, args.si, args.unit)
        if args.raw:
            s = "%s (%s B)" % (s, "{:,}".format(total))
        size_strs.append(s)
    width = max([len(s) for s in size_strs] + [len("TOTAL")])
    for s, (_t, d) in zip(size_strs, rows):
        print("%*s  %s" % (width, s, d))
    total = agg.get(root, 0)
    ts = human(total, args.si, args.unit)
    if args.raw:
        ts = "%s (%s B)" % (ts, "{:,}".format(total))
    print("%s  %s  [TOTAL: %d dir(s), %d file(s)]"
          % (ts.rjust(width), root, len(agg), nfiles))
    for e in errors:
        print("warning: %s" % e, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
