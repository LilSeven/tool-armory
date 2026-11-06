#!/usr/bin/env python3
"""序号重命名（seq-rename）：按排序顺序把文件重命名为 001、002…。

按文件名排序遍历目录中的文件，重命名为「起始号 + 序号*步长」按指定位数
补零的形式（默认 001、002…），扩展名保留。可选 --prefix/--suffix 加在
序号前后。支持 --dry-run 预演。

用法:
    python seq-rename.py <目录> [--start 1] [--step 1] [--width 3] [--prefix P] [--suffix S] [--dry-run]

示例:
    # 预演：从 10 开始、步长 5、4 位编号
    python seq-rename.py ./imgs --start 10 --step 5 --width 4 --dry-run
    # 实际执行：加前缀 img_
    python seq-rename.py ./imgs --prefix img_

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
    p = argparse.ArgumentParser(description="按排序顺序把文件重命名为 001、002…")
    p.add_argument("directory", help="要处理的目录")
    p.add_argument("--start", type=int, default=1, help="起始编号（默认 1）")
    p.add_argument("--step", type=int, default=1, help="步长（默认 1）")
    p.add_argument("--width", type=int, default=3, help="编号位数，不足补零（默认 3）")
    p.add_argument("--prefix", default="", help="加在编号前的文字（默认空）")
    p.add_argument("--suffix", default="", help="加在编号后、扩展名前的文字（默认空）")
    p.add_argument("--dry-run", action="store_true", help="只预演，不实际重命名")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"错误：目录不存在：{directory}", file=sys.stderr)
        return 2
    if args.width < 1 or args.step <= 0:
        print("错误：--width 须 >=1，--step 须 >0", file=sys.stderr)
        return 2

    files = sorted(p for p in directory.iterdir() if p.is_file())
    if not files:
        print("目录中没有可重命名的文件。")
        return 0

    taken: set[str] = set()
    changed = skipped = 0
    for i, path in enumerate(files):
        number = args.start + i * args.step
        new_name = f"{args.prefix}{number:0{args.width}d}{args.suffix}{path.suffix}"
        if new_name == path.name:
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
