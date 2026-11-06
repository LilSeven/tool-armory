#!/usr/bin/env python3
"""前后缀重命名（prefix-suffix-rename）：为一批文件统一添加前缀或后缀。

后缀插在扩展名之前（photo.jpg + _old -> photo_old.jpg），前缀加在文件名
最前面。--use-dirname 可用文件所在目录名作为前缀或后缀。支持 --dry-run 预演。

用法:
    python prefix-suffix-rename.py <目录> [--prefix P] [--suffix S] [--use-dirname {prefix,suffix}] [--dry-run]

示例:
    # 预演：统一加前缀 backup_ 和后缀 _old（插在扩展名之前）
    python prefix-suffix-rename.py ./imgs --prefix backup_ --suffix _old --dry-run
    # 实际执行：用目录名做后缀
    python prefix-suffix-rename.py ./2024报告 --use-dirname suffix

只用 Python 标准库。目标名冲突时跳过并提示。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _is_same_file(a: Path, b: Path) -> bool:
    """Windows 文件系统大小写不敏感：仅大小写不同的两个路径是同一个文件。"""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="为一批文件统一添加前缀或后缀（后缀插在扩展名之前）")
    p.add_argument("directory", help="要处理的目录")
    p.add_argument("--prefix", default="", help="要添加的前缀（默认空）")
    p.add_argument("--suffix", default="", help="要添加的后缀，插在扩展名之前（默认空）")
    p.add_argument("--use-dirname", choices=["prefix", "suffix"], default=None,
                   help="用目录名作为前缀或后缀（与 --prefix/--suffix 叠加）")
    p.add_argument("--dry-run", action="store_true", help="只预演，不实际重命名")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"错误：目录不存在：{directory}", file=sys.stderr)
        return 2
    if not (args.prefix or args.suffix or args.use_dirname):
        print("错误：请至少指定 --prefix、--suffix 或 --use-dirname 之一", file=sys.stderr)
        return 2

    prefix = args.prefix
    suffix = args.suffix
    if args.use_dirname == "prefix":
        prefix = directory.name + prefix
    elif args.use_dirname == "suffix":
        suffix = suffix + directory.name

    files = sorted(p for p in directory.iterdir() if p.is_file())
    if not files:
        print("目录中没有可重命名的文件。")
        return 0

    taken: set[str] = set()
    changed = skipped = 0
    for path in files:
        new_name = f"{prefix}{path.stem}{suffix}{path.suffix}"
        if new_name == path.name or not new_name:
            continue
        candidate = directory / new_name
        if candidate.exists() and not _is_same_file(candidate, path):
            print(f"跳过 {path.name}：目标名已存在 -> {new_name}", file=sys.stderr)
            skipped += 1
            continue
        taken.add(new_name.lower())
        action = "预演" if args.dry_run else "重命名"
        print(f"{action}: {path.name} -> {new_name}")
        if not args.dry_run:
            try:
                path.rename(directory / new_name)
            except OSError as e:
                print(f"失败 {path.name}：{e}", file=sys.stderr)
                skipped += 1
                continue
        changed += 1

    print(f"完成：{'预演' if args.dry_run else '实际'}重命名 {changed} 个文件，跳过 {skipped} 个。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
