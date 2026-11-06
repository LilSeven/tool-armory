#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""缓存目录扫描器（cache-dir-scanner）。

用途:
    递归扫描指定目录，定位 __pycache__、node_modules、venv/.venv、
    .pytest_cache、.tox 等可再生缓存/依赖目录，统计每个目录的文件数
    与磁盘占用，并给出总量。只统计，不删除任何东西。

    命中某个缓存目录后不再深入其内部（其内部的嵌套缓存目录视为已
    包含在父目录占用中，避免重复计数）。

用法:
    python cache-dir-scanner.py <目录> [--only A,B,C] [--add NAME] [--json]

示例:
    python cache-dir-scanner.py .
    python cache-dir-scanner.py D:/code --only __pycache__,node_modules
    python cache-dir-scanner.py ./proj --add build --json

退出码:
    0 = 扫描完成（即使未发现缓存目录）
    2 = 目录不存在或参数错误
"""

import argparse
import json
import os
import sys

# 默认识别的缓存/可再生目录名（比较时转小写）
DEFAULT_CACHE_DIRS = [
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".nox", ".hypothesis", ".eggs", ".cache",
    "node_modules", "bower_components", "web_modules",
    "venv", ".venv",
    ".gradle",
]


def human(nbytes):
    """字节数转人类可读字符串。"""
    size = float(nbytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return "%d B" % int(size)
            return "%.1f %s" % (size, unit)
        size /= 1024.0


def force_utf8_stdio():
    """让中文输出在管道/重定向（如 Git Bash）下不乱码、不报错。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def dir_stats(path):
    """统计目录内文件数与总字节数（符号链接目录不跟进）。"""
    files = 0
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for fn in filenames:
            files += 1
            try:
                total += os.path.getsize(os.path.join(dirpath, fn))
            except OSError:
                pass
    return files, total


def build_parser():
    parser = argparse.ArgumentParser(
        prog="cache-dir-scanner.py",
        description="定位并统计 __pycache__、node_modules、venv 等可再生缓存目录的磁盘占用。",
    )
    parser.add_argument("root", nargs="?", default=".", help="要扫描的目录（默认当前目录）")
    parser.add_argument("--only", default="", metavar="A,B,C",
                        help="只识别这些目录名（逗号分隔），替代默认列表")
    parser.add_argument("--add", action="append", default=[], metavar="NAME",
                        help="在默认列表之外额外识别的目录名（可多次使用，支持逗号分隔）")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    return parser


def main(argv=None):
    force_utf8_stdio()
    args = build_parser().parse_args(argv)

    if not os.path.isdir(args.root):
        print("错误: 目录不存在: %s" % args.root, file=sys.stderr)
        return 2

    if args.only:
        wanted = {n.strip().lower() for n in args.only.split(",") if n.strip()}
    else:
        wanted = set(DEFAULT_CACHE_DIRS)
    for extra in args.add:
        wanted.update(n.strip().lower() for n in extra.split(",") if n.strip())

    found = []
    # 根目录本身就是缓存目录时：整体统计并停止
    if os.path.basename(os.path.abspath(args.root)).lower() in wanted:
        files, size = dir_stats(args.root)
        found.append({"path": args.root, "files": files, "bytes": size})
    else:
        for dirpath, dirnames, _filenames in os.walk(args.root):
            keep = []
            for name in dirnames:
                if name.lower() in wanted:
                    full = os.path.join(dirpath, name)
                    files, size = dir_stats(full)
                    found.append({"path": full, "files": files, "bytes": size})
                else:
                    keep.append(name)
            dirnames[:] = keep
    found.sort(key=lambda rec: -rec["bytes"])
    total = sum(rec["bytes"] for rec in found)
    total_files = sum(rec["files"] for rec in found)

    if args.json:
        print(json.dumps({
            "root": os.path.abspath(args.root),
            "matched_names": sorted(wanted),
            "found_count": len(found),
            "total_files": total_files,
            "total_bytes": total,
            "directories": found,
        }, ensure_ascii=False, indent=2))
        return 0

    print("扫描目录 : %s" % os.path.abspath(args.root))
    print("缓存目录 : %d 个，共 %d 个文件，合计 %s" % (len(found), total_files, human(total)))
    for rec in found:
        print("  %10s  %8d 个文件  %s" % (human(rec["bytes"]), rec["files"], rec["path"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
