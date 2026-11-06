#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""top-large-files.py —— 找出目录树中最大的 N 个文件（仅用 Python 标准库）。

递归扫描目录，按文件大小降序列出前 N 个：完整路径、大小与占扫描总量的百分比。
说明：使用文件名义大小（st_size）；不跟随符号链接目录，符号链接文件本身跳过。

示例命令：
    python top-large-files.py D:\\downloads
    python top-large-files.py D:\\downloads -n 10
    python top-large-files.py . --min-size 100M --si

退出码：0=成功；1=目录不存在或有条目无法访问；2=参数（如 --min-size）不合法。
"""

import argparse
import os
import re
import sys

_SIZE_RE = re.compile(r"^([0-9]*\.?[0-9]+)\s*([KMGT]?)B?$", re.IGNORECASE)


def human(n, si=False):
    x = float(n)
    units = ("B", "kB", "MB", "GB", "TB", "PB") if si else ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    base = 1000.0 if si else 1024.0
    i = 0
    while x >= base and i < len(units) - 1:
        x /= base
        i += 1
    return ("%d %s" % (round(x), units[i])) if i == 0 else ("%.1f %s" % (x, units[i]))


def parse_size(s):
    m = _SIZE_RE.match(s.strip())
    if not m:
        raise ValueError("bad size: %r (examples: 1024, 10K, 100M, 2G)" % s)
    mult = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}[m.group(2).upper()]
    return int(float(m.group(1)) * mult)


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        prog="top-large-files",
        description="Scan a directory tree and rank the N largest files with "
                    "full path, size and share of the scanned total.")
    ap.add_argument("dir", help="directory tree to scan")
    ap.add_argument("-n", "--top", type=int, default=20, metavar="N",
                    help="how many files to list (default 20)")
    ap.add_argument("--min-size", default="0", metavar="SIZE",
                    help="ignore files smaller than SIZE, e.g. 10M (default 0)")
    ap.add_argument("--si", action="store_true", help="use 1000-based units (kB/MB)")
    args = ap.parse_args(argv)

    try:
        minsz = parse_size(args.min_size)
    except ValueError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    if args.top < 1:
        print("error: --top must be >= 1", file=sys.stderr)
        return 2

    root = os.path.abspath(args.dir)
    if not os.path.isdir(root):
        print("error: not a directory: %s" % root, file=sys.stderr)
        return 1

    files = []
    total = 0
    nfiles = 0
    errors = []

    def on_error(err):
        errors.append(str(err))

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error,
                                                followlinks=False):
        dirnames[:] = [d for d in dirnames
                       if not os.path.islink(os.path.join(dirpath, d))]
        for name in filenames:
            p = os.path.join(dirpath, name)
            if os.path.islink(p):
                continue
            try:
                sz = os.lstat(p).st_size
            except OSError as e:
                errors.append(str(e))
                continue
            nfiles += 1
            total += sz
            if sz >= minsz:
                files.append((sz, os.path.abspath(p)))

    print("scanned: %s -- %d file(s), %s total" % (root, nfiles, human(total, args.si)))
    files.sort(key=lambda t: (-t[0], t[1]))
    shown = files[:args.top]
    if not shown:
        print("no files matched (min-size %s)" % args.min_size)
    else:
        print("top %d largest file(s) of %d matching --min-size %s:"
              % (len(shown), len(files), args.min_size))
        for i, (sz, p) in enumerate(shown, 1):
            pct = (sz * 100.0 / total) if total else 0.0
            print("#%-3d %10s  %5.1f%%  %s" % (i, human(sz, args.si), pct, p))
    for e in errors:
        print("warning: %s" % e, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
