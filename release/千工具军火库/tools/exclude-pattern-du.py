#!/usr/bin/env python3
"""排除模式的目录统计（仿 du，支持 --exclude 通配符剪枝）。

递归统计每个子目录的累计占用并按 du 风格输出（大小按文件内容字节数
st_size 计，不含簇对齐开销；目录行含其子目录累计）。遍历过程中用 fnmatch
通配符模式（如 node_modules、.git、*.tmp、build*）直接跳过匹配的目录与
文件：被排除的内容既不递归也不计入，适合估算清理 node_modules 等目录后
的真实体积。不跟随符号链接。

匹配规则：模式同时匹配条目的基本名与相对路径（POSIX 风格），Windows 下
不区分大小写；-e/--exclude 可重复使用。

示例：
  python exclude-pattern-du.py D:/proj --exclude node_modules --exclude .git
  python exclude-pattern-du.py . -e "*.tmp" -e ".git" -s
  python exclude-pattern-du.py a b c -H -a --sort size

退出码：0 正常；1 有读取警告；2 路径不存在。
"""

import argparse
import fnmatch
import os
import sys

UNITS = ("B", "KiB", "MiB", "GiB", "TiB")


def human(n: float) -> str:
    n = float(n)
    for i, unit in enumerate(UNITS):
        if n < 1024 or i == len(UNITS) - 1:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}{UNITS[-1]}"


def is_excluded(name: str, rel: str, patterns) -> bool:
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel, p) for p in patterns)


def scan_dir(path: str, rel: str, patterns, stats: dict, errors: list, all_sizes) -> int:
    """后序遍历：返回该目录累计字节，结果写入 stats；不跟随符号链接。"""
    total = 0
    try:
        entries = sorted(os.scandir(path), key=lambda e: e.name)
    except OSError as exc:
        errors.append(f"无法读取目录 {path}: {exc}")
        stats[path] = 0
        return 0
    for entry in entries:
        erel = f"{rel}/{entry.name}" if rel else entry.name
        try:
            if entry.is_dir(follow_symlinks=False):
                if not is_excluded(entry.name, erel, patterns):
                    total += scan_dir(entry.path, erel, patterns, stats, errors, all_sizes)
            elif entry.is_file(follow_symlinks=False):
                if not is_excluded(entry.name, erel, patterns):
                    size = entry.stat(follow_symlinks=False).st_size
                    total += size
                    if all_sizes is not None:
                        all_sizes[entry.path] = size
        except OSError as exc:
            errors.append(f"无法访问 {entry.path}: {exc}")
    stats[path] = total
    return total


def main(argv=None) -> int:
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        prog="exclude-pattern-du",
        description="仿 du 的目录占用统计，支持 --exclude 通配符在遍历时跳过目录/文件。",
    )
    parser.add_argument("roots", nargs="*", help="要统计的目录（默认当前目录）")
    parser.add_argument("-e", "--exclude", action="append", default=[], metavar="PATTERN",
                        help="fnmatch 通配符，匹配的目录/文件被跳过（可多次使用）")
    parser.add_argument("-s", "--summarize", action="store_true", help="只显示每个根目录的总计")
    parser.add_argument("-a", "--all-files", action="store_true", help="同时列出每个文件")
    parser.add_argument("-H", "--human", action="store_true", help="人类可读大小（默认显示字节）")
    parser.add_argument("--sort", choices=("path", "size"), default="path", help="排序方式（默认 path）")
    args = parser.parse_args(argv)

    roots = args.roots or ["."]
    stats: dict = {}
    all_sizes: dict = {} if args.all_files else None
    errors: list = []
    valid = [r for r in roots if os.path.isdir(r) or os.path.isfile(r)]
    for r in roots:
        if r not in valid:
            errors.append(f"路径不存在: {r}")
    if not valid:
        for msg in errors:
            print(f"错误: {msg}", file=sys.stderr)
        return 2

    for root in valid:
        if os.path.isfile(root):
            try:
                stats[root] = os.path.getsize(root)
            except OSError as exc:
                errors.append(f"无法访问 {root}: {exc}")
                stats[root] = 0
        else:
            scan_dir(root, "", args.exclude, stats, errors, all_sizes)

    if args.summarize:
        rows = [(stats[r], r) for r in valid]
    elif all_sizes is not None:
        rows = [(size, path) for path, size in all_sizes.items()]
        rows += [(size, path) for path, size in stats.items()]
    else:
        rows = [(size, path) for path, size in stats.items()]

    if args.sort == "size":
        rows.sort(key=lambda r: (-r[0], r[1]))
    else:
        rows.sort(key=lambda r: r[1])
    for size, path in rows:
        text = human(size) if args.human else str(size)
        print(f"{text:>12}  {path}")
    for msg in errors:
        print(f"警告: {msg}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
