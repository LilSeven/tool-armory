#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""压缩包内容清单（archive-inventory）。

用途:
    扫描目录下的 zip / tar 系压缩包（.zip、.tar、.tar.gz/.tgz、
    .tar.bz2/.tbz2、.tar.xz/.txz），不解压即可统计每个包的成员数与
    未压缩总大小，并给出汇总。成员数只计文件成员，不含目录条目。
    损坏的包记为错误并继续处理其余包。

用法:
    python archive-inventory.py <目录> [--ext .jar] [--json]

示例:
    python archive-inventory.py .
    python archive-inventory.py D:/dist --ext .jar --ext .whl
    python archive-inventory.py ./backup --json > archives.json

退出码:
    0 = 扫描完成（损坏包只计入错误项，不影响退出码）
    2 = 目录不存在或参数错误
"""

import argparse
import json
import os
import sys
import tarfile
import zipfile

TAR_SUFFIXES = (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz", ".tar")
ZIP_SUFFIXES = (".zip",)
# 按后缀长度降序匹配，保证 ".tar.gz" 优先于 ".tar"
_SORTED_SUFFIXES = sorted(set(TAR_SUFFIXES) | set(ZIP_SUFFIXES), key=len, reverse=True)


def classify(name, extra_exts=()):
    """按文件名判断压缩包类型；不是压缩包返回 None。"""
    low = name.lower()
    for ext in extra_exts:
        if low.endswith(ext):
            return "zip"
    for suffix in _SORTED_SUFFIXES:
        if low.endswith(suffix):
            return "zip" if suffix in ZIP_SUFFIXES else "tar"
    return None


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


def inspect_zip(path):
    """返回 (文件成员数, 未压缩总字节)。"""
    members = 0
    total = 0
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            members += 1
            total += info.file_size
    return members, total


def inspect_tar(path):
    """返回 (文件成员数, 未压缩总字节)，自动识别 gz/bz2/xz 压缩。"""
    members = 0
    total = 0
    with tarfile.open(path, "r:*") as tf:
        for member in tf:
            if member.isfile():
                members += 1
                total += member.size
    return members, total


def build_parser():
    parser = argparse.ArgumentParser(
        prog="archive-inventory.py",
        description="不解压列出目录下所有 zip/tar 包的成员数与未压缩总大小汇总。",
    )
    parser.add_argument("root", nargs="?", default=".", help="要扫描的目录（默认当前目录）")
    parser.add_argument("--ext", action="append", default=[], metavar="EXT",
                        help="额外按 zip 容器处理的扩展名，如 .jar/.whl（可多次使用）")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    return parser


def main(argv=None):
    force_utf8_stdio()
    args = build_parser().parse_args(argv)

    if not os.path.isdir(args.root):
        print("错误: 目录不存在: %s" % args.root, file=sys.stderr)
        return 2

    extra_exts = []
    for ext in args.ext:
        ext = ext.lower().strip()
        if ext and not ext.startswith("."):
            ext = "." + ext
        if ext:
            extra_exts.append(ext)

    results = []
    for dirpath, _dirnames, filenames in os.walk(args.root):
        for fn in filenames:
            kind = classify(fn, extra_exts)
            if kind is None:
                continue
            path = os.path.join(dirpath, fn)
            try:
                archive_bytes = os.path.getsize(path)
            except OSError:
                archive_bytes = -1
            rec = {"path": path, "format": kind, "archive_bytes": archive_bytes}
            try:
                members, total = inspect_zip(path) if kind == "zip" else inspect_tar(path)
                rec["members"] = members
                rec["uncompressed_bytes"] = total
            except Exception as exc:  # 损坏包：记录错误，继续处理
                rec["error"] = "%s: %s" % (type(exc).__name__, exc)
            results.append(rec)
    results.sort(key=lambda rec: rec["path"])

    ok = [rec for rec in results if "error" not in rec]
    bad = [rec for rec in results if "error" in rec]
    members_total = sum(rec["members"] for rec in ok)
    uncomp_total = sum(rec["uncompressed_bytes"] for rec in ok)

    if args.json:
        print(json.dumps({
            "root": os.path.abspath(args.root),
            "archive_count": len(results),
            "ok_count": len(ok),
            "error_count": len(bad),
            "totals": {"members": members_total, "uncompressed_bytes": uncomp_total},
            "archives": results,
        }, ensure_ascii=False, indent=2))
        return 0

    print("扫描目录 : %s" % os.path.abspath(args.root))
    print("压缩包   : %d 个（成功 %d，损坏 %d）；成员合计 %d，未压缩合计 %s"
          % (len(results), len(ok), len(bad), members_total, human(uncomp_total)))
    if results:
        print("-" * 78)
        print("  %-4s %8s %14s %12s %9s  %s"
              % ("类型", "成员数", "未压缩大小", "包大小", "压缩至", "路径"))
        for rec in ok:
            if rec["uncompressed_bytes"] > 0 and rec["archive_bytes"] >= 0:
                ratio = "%5.1f%%" % (100.0 * rec["archive_bytes"] / rec["uncompressed_bytes"])
            else:
                ratio = "    -"
            print("  %-4s %8d %14s %12s %9s  %s"
                  % (rec["format"], rec["members"], human(rec["uncompressed_bytes"]),
                     human(max(rec["archive_bytes"], 0)), ratio, rec["path"]))
        for rec in bad:
            print("  %-4s %8s %14s %12s %9s  %s"
                  % (rec["format"], "-", "-", human(max(rec["archive_bytes"], 0)), "-", rec["path"]))
            print("      错误: %s" % rec["error"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
