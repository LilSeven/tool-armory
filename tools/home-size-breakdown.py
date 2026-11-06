#!/usr/bin/env python3
"""用户目录占用分解 (home-size-breakdown) —— 按一级子目录分解用户主目录的磁盘占用并降序排列。

用途:
    遍历用户主目录（os.path.expanduser("~")，可用 --dir 覆盖），统计每个一级子目录
    占用的磁盘空间（文件 st_size 字节合计，即逻辑大小而非簇分配大小）；主目录根下的
    散文件归入“(根目录文件)”一项；按占用降序排列并给出占比。
    符号链接按链接本身大小统计（不跟随，避免重复计数）；无权限的项跳过并计数。
    --top N 只显示前 N 行；--json 输出机器可读结果。只读统计，不删除、不修改任何文件。

示例命令:
    python home-size-breakdown.py                 # 分解用户主目录
    python home-size-breakdown.py --dir /tmp/demo --top 5
    python home-size-breakdown.py --json

只依赖 Python 标准库；只读统计，不删除、不修改任何文件。
"""

import argparse
import json
import os
import sys


def _force_utf8_stdout():
    """管道/重定向场景下尽量以 UTF-8 输出，避免 Windows 默认码页导致乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (stream.encoding or "").lower().replace("-", "")
            if enc and enc != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def human(nbytes):
    """字节数 -> 人类可读字符串（KiB/MiB/GiB/TiB）。"""
    size = float(nbytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024.0 or unit == "TiB":
            return "%.1f %s" % (size, unit)
        size /= 1024.0
    return "%.1f TiB" % size


def dir_size(path):
    """递归统计目录内文件字节数，返回 (总字节, 文件数, 跳过数)。"""
    total = 0
    files = 0
    skipped = 0
    for dirpath, _dirnames, filenames in os.walk(path, onerror=lambda _e: None):
        for name in filenames:
            fp = os.path.join(dirpath, name)
            try:
                st = os.lstat(fp)  # 不跟随符号链接
            except OSError:
                skipped += 1
                continue
            total += st.st_size
            files += 1
    return total, files, skipped


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="home-size-breakdown",
        description="按一级子目录分解主目录磁盘占用并降序排列（只读统计）",
    )
    parser.add_argument("--dir", default=None, help="要分解的目录（默认为用户主目录）")
    parser.add_argument("--top", type=int, default=0, help="只显示前 N 项（0=全部）")
    parser.add_argument("--json", dest="as_json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)
    _force_utf8_stdout()

    root = os.path.abspath(args.dir) if args.dir else os.path.expanduser("~")
    if not os.path.isdir(root):
        print("目录不存在: %s" % root, file=sys.stderr)
        return 1

    try:
        entries = list(os.scandir(root))
    except OSError as exc:
        print("无法读取目录 %s: %s" % (root, exc), file=sys.stderr)
        return 1

    rows = []
    skipped = 0
    root_files = 0
    root_bytes = 0
    for entry in entries:
        try:
            if entry.is_dir(follow_symlinks=False):
                size, files, sk = dir_size(entry.path)
                skipped += sk
                rows.append({"name": entry.name, "bytes": size, "files": files})
            elif entry.is_file(follow_symlinks=False):
                root_bytes += entry.stat(follow_symlinks=False).st_size
                root_files += 1
        except OSError:
            skipped += 1
    if root_files:
        rows.append({"name": "(根目录文件)", "bytes": root_bytes, "files": root_files})

    rows.sort(key=lambda r: r["bytes"], reverse=True)
    total = sum(r["bytes"] for r in rows)
    for r in rows:
        r["percent"] = round(r["bytes"] * 100.0 / total, 1) if total else 0.0

    if args.as_json:
        print(json.dumps({"root": root, "total_bytes": total, "entries": rows,
                          "skipped": skipped}, ensure_ascii=False, indent=2))
        return 0

    shown = rows[:args.top] if args.top and args.top > 0 else rows
    print("目录: %s" % root)
    print("合计: %s | 一级条目 %d 个 | 文件 %d 个 | 跳过 %d 项"
          % (human(total), len(rows), sum(r["files"] for r in rows), skipped))
    width = max([len(r["name"]) for r in shown] + [12])
    print("  %-*s  %10s  %6s  %s" % (width, "条目", "大小", "占比", "占用示意"))
    for r in shown:
        bar = "#" * int(r["percent"] / 2.0)
        print("  %-*s  %10s  %5.1f%%  %s"
              % (width, r["name"], human(r["bytes"]), r["percent"], bar))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
