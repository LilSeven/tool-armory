#!/usr/bin/env python3
"""临时备份文件清理：按模式（~ 结尾、.tmp、.bak、.swp 等）查找并清理编辑器与程序留下的临时文件。

用途
    在目录（默认递归）中查找常见临时/备份文件并删除：
    *~、~*、*.tmp、*.bak、*.swp、*.swo、*.swn、.DS_Store、Thumbs.db、
    *.orig、*.rej、*.$$? 等，也可用 --pattern 自定义 glob。
    默认只列出（预演，不改动磁盘）；加 --delete 才真正删除。

示例命令
    python temp-file-cleaner.py ./project                # 预演：列出找到的临时文件
    python temp-file-cleaner.py ./project --delete       # 实际删除
    python temp-file-cleaner.py . --pattern "*.cache"    # 追加自定义模式（默认已递归）
    python temp-file-cleaner.py . --no-recursive -n      # 只扫当前目录，显示大小

参数
    directory      要清理的目录
    --delete       实际删除（缺省为预演）
    -p/--pattern   追加自定义 glob 模式（可多次使用）
    --no-recursive 不递归子目录
    -n/--show-size 在列表中显示文件大小
"""
import argparse
import fnmatch
import os
import sys

DEFAULT_PATTERNS = [
    "*~", "~*", "*.tmp", "*.temp", "*.bak", "*.swp", "*.swo", "*.swn",
    "*.orig", "*.rej", ".DS_Store", "Thumbs.db", "*.~*",
]

def find_temp_files(directory, patterns, recursive):
    found = []
    if recursive:
        walker = os.walk(directory)
    else:
        # 非递归：实际列出目录内容，仅取文件（不进入子目录）
        names = [e for e in os.listdir(directory)
                 if os.path.isfile(os.path.join(directory, e))]
        walker = [(directory, [], names)]
    for root, dirs, names in walker:
        if recursive:
            dirs[:] = sorted(d for d in dirs if d not in (".git", "__pycache__"))
        for name in sorted(names):
            if any(fnmatch.fnmatch(name, pat) for pat in patterns):
                found.append(os.path.join(root, name))
    return found

def main(argv=None):
    ap = argparse.ArgumentParser(description="查找并清理编辑器/程序留下的临时与备份文件，默认预演")
    ap.add_argument("directory", help="要清理的目录")
    ap.add_argument("--delete", action="store_true", help="实际删除（缺省为预演）")
    ap.add_argument("-p", "--pattern", action="append", default=[], metavar="GLOB",
                    help="追加自定义 glob 模式，可多次使用")
    ap.add_argument("--no-recursive", action="store_true", help="不递归子目录")
    ap.add_argument("-n", "--show-size", action="store_true", help="显示文件大小")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.directory):
        print("错误：目录不存在：%s" % args.directory)
        return 2

    patterns = DEFAULT_PATTERNS + args.pattern
    found = find_temp_files(args.directory, patterns, not args.no_recursive)

    if not found:
        print("未发现临时/备份文件（模式：%s）。" % ", ".join(patterns))
        return 0

    total_bytes = 0
    for path in found:
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        total_bytes += size
        if args.show_size:
            print("  [%s] %s" % (format_size(size), path))
        else:
            print("  %s" % path)

    if not args.delete:
        print("共 %d 个临时文件，约 %s。预演结束，未删除；确认后加 --delete 执行。"
              % (len(found), format_size(total_bytes)))
        return 0

    deleted = failed = 0
    for path in found:
        try:
            os.remove(path)
            deleted += 1
        except OSError as e:
            failed += 1
            print("  [删除失败] %s: %s" % (path, e))
    if failed:
        print("已删除 %d 个，失败 %d 个（保留原文件）。" % (deleted, failed))
        return 1
    print("已删除 %d 个临时文件，共释放约 %s。" % (deleted, format_size(total_bytes)))
    return 0

def format_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.1f %s" % (n, unit) if unit != "B" else "%d B" % n
        n /= 1024.0
    return "%d B" % n

if __name__ == "__main__":
    sys.exit(main())
