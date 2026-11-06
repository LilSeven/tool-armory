#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""垃圾文件查找器（junk-file-finder）。

用途:
    递归扫描指定目录，找出常见垃圾/临时/备份文件，并按类别汇总数量
    与可清理空间。只报告，不删除任何文件。

识别类型:
    *.tmp / *.temp                     临时文件
    *~ / *.bak / *.old                 备份文件
    ~$* / .~*                          Office 锁文件 / emacs 备份
    *.swp / *.swo / *.orig / *.rej     vim 交换文件与补丁/合并残留
    Thumbs.db / .DS_Store / ._*        Windows 缩略图与 macOS 垃圾

用法:
    python junk-file-finder.py <目录> [--list] [--limit N] [--json]

示例:
    python junk-file-finder.py .
    python junk-file-finder.py D:/work --list --limit 30
    python junk-file-finder.py ./project --json > junk-report.json

退出码:
    0 = 扫描完成（无论是否发现垃圾文件）
    2 = 目录不存在或参数错误
"""

import argparse
import json
import os
import sys

# 精确文件名匹配（比较时转小写，兼容 Windows 大小写不敏感）
JUNK_NAMES = {
    "thumbs.db": "缩略图缓存(Thumbs.db)",
    ".ds_store": "macOS 桌面服务(.DS_Store)",
}
# 前缀匹配: (前缀, 类别)
NAME_PREFIXES = [
    ("~$", "Office 锁文件(~$*)"),
    (".~", "备份文件(.~*)"),
]
# 后缀匹配: (后缀, 类别)
NAME_SUFFIXES = [
    ("~", "备份文件(*~)"),
]
# 扩展名匹配
EXTENSIONS = {
    ".tmp": "临时文件(*.tmp)",
    ".temp": "临时文件(*.temp)",
    ".bak": "备份文件(*.bak)",
    ".old": "旧版本文件(*.old)",
    ".swp": "vim 交换文件(*.swp)",
    ".swo": "vim 交换文件(*.swo)",
    ".orig": "合并残留(*.orig)",
    ".rej": "补丁残留(*.rej)",
}


def classify(name):
    """按文件名判断垃圾类别；不是垃圾返回 None。"""
    low = name.lower()
    if low in JUNK_NAMES:
        return JUNK_NAMES[low]
    for prefix, label in NAME_PREFIXES:
        if low.startswith(prefix):
            return label
    for suffix, label in NAME_SUFFIXES:
        if len(low) > len(suffix) and low.endswith(suffix):
            return label
    ext = os.path.splitext(low)[1]
    if ext in EXTENSIONS:
        return EXTENSIONS[ext]
    if len(low) > 2 and low.startswith("._"):
        return "macOS AppleDouble(._*)"
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


def scan(root):
    """遍历目录，返回 (垃圾文件记录列表, 扫描文件总数)。"""
    records = []
    scanned = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            scanned += 1
            category = classify(fn)
            if category is None:
                continue
            path = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(path)
            except OSError:
                size = -1
            records.append({"path": path, "size": size, "category": category})
    return records, scanned


def build_parser():
    parser = argparse.ArgumentParser(
        prog="junk-file-finder.py",
        description="找出 .tmp、~备份、Thumbs.db、.DS_Store 等垃圾文件并汇总可清理空间（只报告，不删除）。",
    )
    parser.add_argument("root", nargs="?", default=".", help="要扫描的目录（默认当前目录）")
    parser.add_argument("--list", action="store_true", help="按大小降序列出垃圾文件")
    parser.add_argument("--limit", type=int, default=200, metavar="N",
                        help="--list 最多显示条数（默认 200，0=全部）")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出完整结果")
    return parser


def main(argv=None):
    force_utf8_stdio()
    args = build_parser().parse_args(argv)

    if not os.path.isdir(args.root):
        print("错误: 目录不存在: %s" % args.root, file=sys.stderr)
        return 2

    records, scanned = scan(args.root)
    total_size = sum(max(rec["size"], 0) for rec in records)

    if args.json:
        summary = {}
        for rec in records:
            cnt, size = summary.get(rec["category"], (0, 0))
            summary[rec["category"]] = (cnt + 1, size + max(rec["size"], 0))
        print(json.dumps({
            "root": os.path.abspath(args.root),
            "scanned_files": scanned,
            "junk_count": len(records),
            "reclaimable_bytes": total_size,
            "categories": {cat: {"count": cnt, "bytes": size}
                           for cat, (cnt, size) in sorted(summary.items())},
            "files": records,
        }, ensure_ascii=False, indent=2))
        return 0

    print("扫描目录 : %s" % os.path.abspath(args.root))
    print("扫描文件 : %d 个" % scanned)
    print("垃圾文件 : %d 个，可清理 %s" % (len(records), human(total_size)))
    if records:
        summary = {}
        for rec in records:
            cnt, size = summary.get(rec["category"], (0, 0))
            summary[rec["category"]] = (cnt + 1, size + max(rec["size"], 0))
        print("-" * 62)
        for cat, (cnt, size) in sorted(summary.items(), key=lambda item: -item[1][1]):
            print("  %-26s %5d 个  %10s" % (cat, cnt, human(size)))
        if args.list:
            ordered = sorted(records, key=lambda rec: -max(rec["size"], 0))
            if args.limit > 0:
                ordered = ordered[: args.limit]
            print("-" * 62)
            for rec in ordered:
                shown = human(rec["size"]) if rec["size"] >= 0 else "未知"
                print("  %10s  %s" % (shown, rec["path"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
