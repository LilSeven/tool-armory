#!/usr/bin/env python3
"""递归目录正则搜索 — 递归扫描目录按正则搜行，输出 文件名:行号:内容 并统计每文件命中数。

用法：
  python -I regex-grepdir.py 'def \\w+' K:\\WorkAreaZcode\\tool-armory
  python -I regex-grepdir.py 'TODO' ./src --include '*.py' --summary
  python -I regex-grepdir.py 'import re' . --ignore-case --no-content --summary
退出码：0 找到命中；1 无命中；2 参数/IO 错误。
"""
import argparse
import fnmatch
import os
import re
import sys


def iter_files(root: str, include: str, exclude_hidden: bool):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        if exclude_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fname in sorted(filenames):
            if exclude_hidden and fname.startswith("."):
                continue
            if include and not fnmatch.fnmatch(fname, include):
                continue
            yield os.path.join(dirpath, fname)


def main(argv=None):
    ap = argparse.ArgumentParser(description="递归目录正则搜索并统计命中")
    ap.add_argument("pattern", help="正则表达式")
    ap.add_argument("path", nargs="?", default=".", help="目录或单文件（默认当前目录）")
    ap.add_argument("--include", default="*", help="文件名通配（默认 *）")
    ap.add_argument("--ignore-case", action="store_true")
    ap.add_argument("--summary", action="store_true", help="结尾打印每文件命中数统计")
    ap.add_argument("--no-content", action="store_true", help="不打印行内容，只统计")
    ap.add_argument("--max-bytes", type=int, default=2 * 1024 * 1024,
                    help="跳过超过该字节数的文件（默认 2MB）")
    ap.add_argument("-e", "--encoding", default="utf-8", help="文件编码（默认 utf-8，容错）")
    args = ap.parse_args(argv)

    flags = re.IGNORECASE if args.ignore_case else 0
    try:
        rx = re.compile(args.pattern, flags)
    except re.error as exc:
        print(f"错误：正则编译失败: {exc}", file=sys.stderr)
        return 2
    if not os.path.exists(args.path):
        print(f"错误：路径不存在: {args.path}", file=sys.stderr)
        return 2

    counts = {}
    total = 0
    # relpath 的 start 必须与被扫文件同盘，固定为扫描根（单文件时为其所在目录）
    start = os.path.abspath(args.path)
    if os.path.isfile(start):
        start = os.path.dirname(start)
    for path in iter_files(args.path, args.include, exclude_hidden=True):
        try:
            if os.path.getsize(path) > args.max_bytes:
                continue
            with open(path, "r", encoding=args.encoding, errors="replace") as f:
                hits = 0
                for lineno, line in enumerate(f, 1):
                    if rx.search(line):
                        hits += 1
                        total += 1
                        if not args.no_content:
                            rel = os.path.relpath(path, start)
                            print(f"{rel}:{lineno}:{line.rstrip(chr(10))}")
        except (OSError, UnicodeError):
            continue  # 跳过无法读取/二进制文件
        if hits:
            counts[path] = hits

    if args.summary:
        print("-" * 40)
        for path, hits in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"{hits:5d}  {path}")
        print(f"合计 {total} 处命中，{len(counts)} 个文件")

    if total == 0:
        print(f"（'{args.pattern}' 无命中）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
