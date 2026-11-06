#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""目录结构对比器（dir-compare）。

递归对比两个目录树，报告：
  * 只在 A / 只在 B 中存在的文件；
  * 两边都有、但大小或修改时间不同的文件（任一不同即算 changed，并注明
    差异来自 size 还是 mtime；--size-only 可忽略 mtime）。

修改时间比较允许 --mtime-tol 秒的容差（默认 2 秒，兼容复制造成的轻微
时间戳偏移）。符号链接不参与比较。

用法示例：
    python dir-compare.py K:\\backup K:\\current
    python dir-compare.py K:\\backup K:\\current --size-only
    python dir-compare.py K:\\backup K:\\current --mtime-tol 0 --fail-on-diff
    python dir-compare.py K:\\backup K:\\current --json

退出码：0 完成比较（无论是否有差异）；出现差异且指定了 --fail-on-diff 时
        为 2；参数或路径错误为 2（argparse）。
"""

import argparse
import json
import os
import stat
import sys
import time


def snapshot(root):
    """返回 {相对路径: (大小, mtime)}。"""
    files = {}
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None,
                                                followlinks=False):
        for name in filenames:
            path = os.path.join(dirpath, name)
            try:
                st = os.stat(path, follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISLNK(st.st_mode):
                continue
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            files[rel] = (st.st_size, st.st_mtime)
    return files


def fmt_time(t):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    parser = argparse.ArgumentParser(
        description="Compare two directory trees: extra/missing files and "
                    "files differing in size or mtime.")
    parser.add_argument("dir_a", help="left directory (reference)")
    parser.add_argument("dir_b", help="right directory")
    parser.add_argument("--size-only", action="store_true",
                        help="ignore modification times")
    parser.add_argument("--mtime-tol", type=float, default=2.0, metavar="SEC",
                        help="mtime tolerance in seconds (default: 2)")
    parser.add_argument("--fail-on-diff", action="store_true",
                        help="exit with code 2 when any difference is found")
    parser.add_argument("--json", action="store_true",
                        help="print JSON instead of the human-readable report")
    args = parser.parse_args(argv)

    a_root = os.path.abspath(args.dir_a)
    b_root = os.path.abspath(args.dir_b)
    if not os.path.isdir(a_root):
        parser.error("not a directory: %s" % args.dir_a)
    if not os.path.isdir(b_root):
        parser.error("not a directory: %s" % args.dir_b)

    a = snapshot(a_root)
    b = snapshot(b_root)

    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    changed = []
    identical = 0
    for rel in sorted(set(a) & set(b)):
        sa, ma = a[rel]
        sb, mb = b[rel]
        reasons = []
        if sa != sb:
            reasons.append("size")
        if not args.size_only and abs(ma - mb) > args.mtime_tol:
            reasons.append("mtime")
        if reasons:
            changed.append({"path": rel, "reasons": reasons,
                            "a_size": sa, "b_size": sb,
                            "a_mtime": fmt_time(ma), "b_mtime": fmt_time(mb)})
        else:
            identical += 1

    has_diff = bool(only_a or only_b or changed)
    if args.json:
        print(json.dumps({"a": a_root, "b": b_root,
                          "only_in_a": only_a, "only_in_b": only_b,
                          "changed": changed,
                          "summary": {"files_a": len(a), "files_b": len(b),
                                      "only_a": len(only_a), "only_b": len(only_b),
                                      "changed": len(changed),
                                      "identical": identical}},
                         ensure_ascii=False, indent=2))
    else:
        print("Comparing:\n  A = %s\n  B = %s" % (a_root, b_root))
        if only_a:
            print("\nOnly in A (%d):" % len(only_a))
            for rel in only_a:
                print("  - %s" % rel)
        if only_b:
            print("\nOnly in B (%d):" % len(only_b))
            for rel in only_b:
                print("  + %s" % rel)
        if changed:
            print("\nChanged (%d):" % len(changed))
            for c in changed:
                detail = []
                if "size" in c["reasons"]:
                    detail.append("size %d -> %d" % (c["a_size"], c["b_size"]))
                if "mtime" in c["reasons"]:
                    detail.append("mtime %s -> %s" % (c["a_mtime"], c["b_mtime"]))
                print("  ~ %-24s %s" % (c["path"], "; ".join(detail)))
        if not has_diff:
            print("\nNo differences.")
        print("\nSummary: A has %d files, B has %d | only A: %d, only B: %d, "
              "changed: %d, identical: %d"
              % (len(a), len(b), len(only_a), len(only_b), len(changed), identical))
    return 2 if (args.fail_on_diff and has_diff) else 0


if __name__ == "__main__":
    sys.exit(main())
