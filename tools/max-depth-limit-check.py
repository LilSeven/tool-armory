#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深度与数量告警（max-depth-limit-check）。

检查目录树中两类“不健康”的位置并告警：
  * 嵌套过深：目录深度（根目录为 0，直接子目录为 1，依此类推）> --max-depth；
  * 单目录文件过多：某目录下的直接子文件数（不含子目录）> --max-files。

默认即使发现告警也以退出码 0 结束（告警只是报告）；加 --strict 后，存在
告警则以退出码 2 结束，便于接入 CI 或定时任务。

用法示例：
    python max-depth-limit-check.py K:\\data --max-depth 6 --max-files 300
    python max-depth-limit-check.py K:\\data --max-depth 4 --max-files 10 --strict
    python max-depth-limit-check.py K:\\data --json

退出码：0 无告警（或未加 --strict）；2 有告警且加了 --strict；2 参数或路径
        错误（argparse）。
"""

import argparse
import json
import os
import sys


def check(root, max_depth, max_files):
    violations = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None,
                                                followlinks=False):
        scanned += 1
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > max_depth:
            violations.append({"path": dirpath, "kind": "depth",
                               "value": depth, "limit": max_depth})
        if len(filenames) > max_files:
            violations.append({"path": dirpath, "kind": "file-count",
                               "value": len(filenames), "limit": max_files})
    return violations, scanned


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    parser = argparse.ArgumentParser(
        description="Warn about directories nested deeper than --max-depth "
                    "or holding more than --max-files direct files.")
    parser.add_argument("root", help="directory to check")
    parser.add_argument("--max-depth", type=int, default=8, metavar="N",
                        help="maximum allowed nesting depth (default: 8)")
    parser.add_argument("--max-files", type=int, default=500, metavar="N",
                        help="maximum allowed direct files per directory (default: 500)")
    parser.add_argument("--strict", action="store_true",
                        help="exit with code 2 when violations are found")
    parser.add_argument("--json", action="store_true",
                        help="print JSON instead of the human-readable report")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        parser.error("not a directory: %s" % args.root)

    violations, scanned = check(root, args.max_depth, args.max_files)

    if args.json:
        print(json.dumps({"root": root, "max_depth": args.max_depth,
                          "max_files": args.max_files, "scanned": scanned,
                          "violations": violations, "count": len(violations)},
                         ensure_ascii=False, indent=2))
    elif violations:
        print("Checking %s (max-depth=%d, max-files=%d)"
              % (root, args.max_depth, args.max_files))
        for v in violations:
            print("[WARN] %-12s %5d > %-5d : %s"
                  % (v["kind"], v["value"], v["limit"], v["path"]))
        print("%d violation(s) found in %d directories."
              % (len(violations), scanned))
    else:
        print("Checking %s (max-depth=%d, max-files=%d)"
              % (root, args.max_depth, args.max_files))
        print("OK: no violations. %d directories scanned." % scanned)
    return 2 if (args.strict and violations) else 0


if __name__ == "__main__":
    sys.exit(main())
