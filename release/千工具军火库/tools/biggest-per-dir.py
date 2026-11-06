#!/usr/bin/env python3
"""各目录最大文件：递归列出每个目录下最大的一个文件及其占该目录总量的比例。

默认按 du 口径：每个目录的"总量"= 其整个子树所有文件大小之和（st_size），
"最大文件"= 子树中最大的那个文件——用于发现"哪个目录被一个大文件撑大"。
加 --direct 则只统计直接位于目录内的文件（不含子目录内容）。

每行输出：占比  大小  目录 -> 最大文件（目录下没有文件时显示 -）。
不跟随符号链接。

示例：
  python biggest-per-dir.py D:/data
  python biggest-per-dir.py . --direct --sort percent
  python biggest-per-dir.py a b -H --sort size

退出码：0 正常；1 有读取警告；2 路径不存在。
"""

import argparse
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


def walk_dir(path: str, direct: bool, records: list, errors: list):
    """后序遍历；返回 (该目录文件总字节, 最大文件 (size, path) 或 None)。"""
    total = 0
    best = None
    try:
        entries = sorted(os.scandir(path), key=lambda e: e.name)
    except OSError as exc:
        errors.append(f"无法读取目录 {path}: {exc}")
        records.append((path, 0, None))
        return 0, None
    for entry in entries:
        try:
            if entry.is_dir(follow_symlinks=False):
                sub_total, sub_best = walk_dir(entry.path, direct, records, errors)
                if not direct:
                    total += sub_total
                    if sub_best is not None and (best is None or sub_best[0] > best[0]):
                        best = sub_best
            elif entry.is_file(follow_symlinks=False):
                size = entry.stat(follow_symlinks=False).st_size
                total += size
                if best is None or size > best[0]:
                    best = (size, entry.path)
        except OSError as exc:
            errors.append(f"无法访问 {entry.path}: {exc}")
    records.append((path, total, best))
    return total, best


def main(argv=None) -> int:
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        prog="biggest-per-dir",
        description="递归列出每个目录下最大的一个文件及其占该目录总量的比例。",
    )
    parser.add_argument("roots", nargs="*", help="要扫描的目录（默认当前目录）")
    parser.add_argument("--direct", action="store_true",
                        help="只统计目录内直接文件，不含子目录（默认按整个子树统计）")
    parser.add_argument("-H", "--human", action="store_true", help="人类可读大小（默认字节）")
    parser.add_argument("--sort", choices=("size", "percent", "path"), default="size",
                        help="排序方式（默认 size 降序）")
    args = parser.parse_args(argv)

    roots = args.roots or ["."]
    records: list = []
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
                size = os.path.getsize(root)
            except OSError as exc:
                errors.append(f"无法访问 {root}: {exc}")
                size = 0
            records.append((root, size, (size, root) if size else None))
        else:
            walk_dir(root, args.direct, records, errors)

    print(f"{'percent':>7}  {'size':>12}  directory -> largest file")
    rows = []
    for path, total, best in records:
        pct = (best[0] / total * 100.0) if (best and total > 0) else 0.0
        rows.append((pct, total, path, best[1] if best else None))
    if args.sort == "percent":
        rows.sort(key=lambda r: (-r[0], r[2]))
    elif args.sort == "path":
        rows.sort(key=lambda r: r[2])
    else:
        rows.sort(key=lambda r: (-r[1], r[2]))
    for pct, total, path, best_path in rows:
        size_text = human(total) if args.human else str(total)
        print(f"{pct:6.1f}%  {size_text:>12}  {path}  ->  {best_path or '-'}")
    for msg in errors:
        print(f"警告: {msg}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
