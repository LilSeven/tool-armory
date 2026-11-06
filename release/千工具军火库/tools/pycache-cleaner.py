#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字节码缓存清理器（pycache-cleaner）。

用途:
    预演式清理 Python 字节码缓存：默认只做"演练"，列出将要删除的
    __pycache__ 目录内文件与散落的 *.pyc / *.pyo 文件，并汇总可释放
    空间；加 --execute（或 -y）才真正删除。删除后若 __pycache__ 目录
    已空则一并移除。

用法:
    python pycache-cleaner.py <目录> [--execute] [--json]

示例:
    python pycache-cleaner.py .                 # 预演，不改动任何文件
    python pycache-cleaner.py ./proj --execute  # 真正删除
    python pycache-cleaner.py ./proj --json     # 预演结果以 JSON 输出

退出码:
    0 = 完成（预演或删除；个别文件删除失败只记入 errors，不影响退出码）
    2 = 目录不存在或参数错误
"""

import argparse
import json
import os
import sys


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


def collect(root):
    """收集清理目标。

    返回 (groups, strays):
      groups: __pycache__ 目录列表 [{"dir": str, "files": [(路径, 大小), ...]}]
      strays: __pycache__ 之外的散落 .pyc/.pyo [{"path": str, "size": int}]
    """
    groups = []
    strays = []
    for dirpath, dirnames, filenames in os.walk(root):
        if os.path.basename(dirpath).lower() == "__pycache__":
            entries = []
            for fn in filenames:
                path = os.path.join(dirpath, fn)
                try:
                    entries.append((path, os.path.getsize(path)))
                except OSError:
                    pass
            groups.append({"dir": dirpath, "files": entries})
            dirnames[:] = []  # __pycache__ 内部不再下钻
            continue
        for fn in filenames:
            if fn.lower().endswith((".pyc", ".pyo")):
                path = os.path.join(dirpath, fn)
                try:
                    strays.append({"path": path, "size": os.path.getsize(path)})
                except OSError:
                    pass
    return groups, strays


def build_result(root, execute):
    """生成结果字典：execute=False 为预演，True 为真正删除。"""
    groups, strays = collect(root)
    errors = []
    freed = 0
    removed_files = 0
    removed_dirs = 0
    if execute:
        for group in groups:
            for path, size in group["files"]:
                try:
                    os.remove(path)
                    freed += size
                    removed_files += 1
                except OSError as exc:
                    errors.append({"path": path, "error": str(exc)})
            try:
                os.rmdir(group["dir"])  # 目录非空则保留
                removed_dirs += 1
            except OSError:
                pass
        for rec in strays:
            try:
                os.remove(rec["path"])
                freed += rec["size"]
                removed_files += 1
            except OSError as exc:
                errors.append({"path": rec["path"], "error": str(exc)})

    total_bytes = sum(size for g in groups for _p, size in g["files"])
    total_bytes += sum(rec["size"] for rec in strays)
    total_files = sum(len(g["files"]) for g in groups) + len(strays)
    return {
        "root": os.path.abspath(root),
        "mode": "execute" if execute else "dry-run",
        "pycache_dirs": [
            {
                "dir": g["dir"],
                "bytes": sum(size for _p, size in g["files"]),
                "files": [{"path": p, "size": s} for p, s in g["files"]],
            }
            for g in groups
        ],
        "stray_files": strays,
        "totals": {"files": total_files, "bytes": total_bytes},
        "executed": execute,
        "removed_files": removed_files,
        "removed_dirs": removed_dirs,
        "freed_bytes": freed,
        "errors": errors,
    }


def build_parser():
    parser = argparse.ArgumentParser(
        prog="pycache-cleaner.py",
        description="预演式清理 __pycache__ 与 .pyc 文件，输出将释放的空间与文件清单（--execute 才真删）。",
    )
    parser.add_argument("root", nargs="?", default=".", help="要清理的目录（默认当前目录）")
    parser.add_argument("-y", "--execute", action="store_true",
                        help="真正执行删除（默认只预演）")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    return parser


def main(argv=None):
    force_utf8_stdio()
    args = build_parser().parse_args(argv)

    if not os.path.isdir(args.root):
        print("错误: 目录不存在: %s" % args.root, file=sys.stderr)
        return 2

    result = build_result(args.root, args.execute)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    totals = result["totals"]
    print("扫描目录 : %s" % result["root"])
    if not args.execute:
        print("模式     : 预演（未删除任何文件；加 --execute 执行删除）")
    print("目标     : __pycache__ 目录 %d 个，散落 .pyc/.pyo 文件 %d 个，"
          "共 %d 个文件，可释放 %s"
          % (len(result["pycache_dirs"]), len(result["stray_files"]),
             totals["files"], human(totals["bytes"])))
    for group in result["pycache_dirs"]:
        print("-" * 62)
        print("[__pycache__] %s（%d 个文件, %s）"
              % (group["dir"], len(group["files"]), human(group["bytes"])))
        for f in group["files"]:
            print("    %10s  %s" % (human(f["size"]), f["path"]))
    if result["stray_files"]:
        print("-" * 62)
        print("[散落 .pyc/.pyo]")
        for rec in result["stray_files"]:
            print("    %10s  %s" % (human(rec["size"]), rec["path"]))
    if args.execute:
        print("-" * 62)
        print("已删除 %d 个文件，实际释放 %s；移除空 __pycache__ 目录 %d 个"
              % (result["removed_files"], human(result["freed_bytes"]),
                 result["removed_dirs"]))
        if result["errors"]:
            print("失败 %d 个:" % len(result["errors"]))
            for err in result["errors"]:
                print("  %s: %s" % (err["path"], err["error"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
