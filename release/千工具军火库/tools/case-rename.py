#!/usr/bin/env python3
"""大小写规整重命名（case-rename）：批量把文件名转为全小写、全大写或标题式大小写。

可选保留扩展名不动（--keep-ext，默认开启），即只改变主干部分的大小写，
扩展名原样保留。支持 --dry-run 预演。

用法:
    python case-rename.py <目录> --mode {lower,upper,title} [--keep-ext | --no-keep-ext] [--dry-run]

示例:
    # 预演：全部转小写，扩展名不动
    python case-rename.py ./docs --mode lower --dry-run
    # 实际执行：全部转标题式大小写，扩展名一并转换
    python case-rename.py ./docs --mode title --no-keep-ext

只用 Python 标准库。目标名冲突时跳过并提示。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _is_same_file(a: Path, b: Path) -> bool:
    import os
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))


def transform(name: str, mode: str) -> str:
    if mode == "lower":
        return name.lower()
    if mode == "upper":
        return name.upper()
    if mode == "title":
        return " ".join(w.capitalize() if w else w for w in name.split(" "))
    raise ValueError(f"未知模式：{mode}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="批量把文件名转为全小写、全大写或标题式大小写")
    p.add_argument("directory", help="要处理的目录")
    p.add_argument("--mode", required=True, choices=["lower", "upper", "title"],
                   help="lower=全小写，upper=全大写，title=标题式大小写")
    p.add_argument("--keep-ext", dest="keep_ext", action="store_true", default=True,
                   help="扩展名保持原样（默认）")
    p.add_argument("--no-keep-ext", dest="keep_ext", action="store_false",
                   help="扩展名也一并转换大小写")
    p.add_argument("--dry-run", action="store_true", help="只预演，不实际重命名")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"错误：目录不存在：{directory}", file=sys.stderr)
        return 2

    files = sorted(p for p in directory.iterdir() if p.is_file())
    if not files:
        print("目录中没有可重命名的文件。")
        return 0

    taken: set[str] = set()
    changed = skipped = 0
    for path in files:
        stem, ext = path.stem, path.suffix
        new_stem = transform(stem, args.mode)
        new_ext = transform(ext, args.mode) if not args.keep_ext else ext
        new_name = new_stem + new_ext
        if new_name == path.name or not new_name:
            continue
        candidate = directory / new_name
        # Windows 文件系统大小写不敏感：仅大小写不同的目标与源文件是
        # 同一个文件，允许重命名；与其他文件冲突才跳过。
        if candidate.exists() and not _is_same_file(candidate, path):
            print(f"跳过 {path.name}：目标名已存在 -> {new_name}", file=sys.stderr)
            skipped += 1
            continue
        if new_name.lower() in taken:
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
