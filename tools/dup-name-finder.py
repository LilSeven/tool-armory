#!/usr/bin/env python3
"""同名文件查找器：跨目录查找文件名相同（不论内容）的文件，按组输出。

把所有根目录下（递归）的文件按文件名（不含路径）分组，列出成员数达到
阈值的组，附大小与修改时间，用于清理下载与备份残留（同名但内容各异的
副本也能找出来）。默认不区分文件名大小写（与 Windows 文件系统语义一致），
--case-sensitive 严格区分；--match 可先用通配符过滤文件名。不跟随符号链接。

示例：
  python dup-name-finder.py D:/downloads D:/backup
  python dup-name-finder.py . --match "*.mp4" --min-group 3
  python dup-name-finder.py a b --case-sensitive

退出码：0 正常；1 有读取警告；2 路径不存在。
"""

import argparse
import fnmatch
import os
import sys
import time


def walk_files(path: str, files: list, errors: list) -> None:
    try:
        entries = sorted(os.scandir(path), key=lambda e: e.name)
    except OSError as exc:
        errors.append(f"无法读取目录 {path}: {exc}")
        return
    for entry in entries:
        try:
            if entry.is_dir(follow_symlinks=False):
                walk_files(entry.path, files, errors)
            elif entry.is_file(follow_symlinks=False):
                st = entry.stat(follow_symlinks=False)
                files.append((entry.path, st.st_size, st.st_mtime))
        except OSError as exc:
            errors.append(f"无法访问 {entry.path}: {exc}")


def main(argv=None) -> int:
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        prog="dup-name-finder",
        description="跨目录查找文件名相同（不论内容）的文件，用于清理下载与备份残留。",
    )
    parser.add_argument("roots", nargs="*", help="要扫描的目录（默认当前目录）")
    parser.add_argument("--match", metavar="GLOB", help="只考虑文件名匹配此 fnmatch 模式的文件")
    parser.add_argument("--min-group", type=int, default=2, metavar="N",
                        help="只显示成员数 >= N 的组（默认 2）")
    parser.add_argument("--case-sensitive", action="store_true",
                        help="区分文件名大小写（默认不区分）")
    args = parser.parse_args(argv)

    roots = args.roots or ["."]
    errors: list = []
    files: list = []  # (path, size, mtime)
    valid = [r for r in roots if os.path.isdir(r) or os.path.isfile(r)]
    for r in roots:
        if r not in valid:
            errors.append(f"路径不存在: {r}")
    if not valid:
        for msg in errors:
            print(f"错误: {msg}", file=sys.stderr)
        return 2

    for root in valid:
        if os.path.islink(root):
            continue
        if os.path.isfile(root):
            try:
                st = os.stat(root)
                files.append((root, st.st_size, st.st_mtime))
            except OSError as exc:
                errors.append(f"无法访问 {root}: {exc}")
        elif os.path.isdir(root):
            walk_files(root, files, errors)

    files.sort()
    groups: dict = {}
    for path, size, mtime in files:
        name = os.path.basename(path)
        if args.match and not fnmatch.fnmatch(name, args.match):
            continue
        key = name if args.case_sensitive else name.lower()
        groups.setdefault(key, []).append((name, path, size, mtime))

    shown = [g for g in groups.values() if len(g) >= max(1, args.min_group)]
    shown.sort(key=lambda g: (-len(g), g[0][0].lower(), g[0][0]))
    for group in shown:
        name = group[0][0]
        total = sum(item[2] for item in group)
        print(f"[{name}] {len(group)} 个文件, 共 {total} 字节")
        for _, path, size, mtime in sorted(group, key=lambda item: item[1]):
            stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
            print(f"  {stamp}  {size:>12}  {path}")
    print(f"共 {len(shown)} 组同名文件，涉及 {sum(len(g) for g in shown)} 个文件")
    for msg in errors:
        print(f"警告: {msg}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
