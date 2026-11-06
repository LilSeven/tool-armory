#!/usr/bin/env python3
"""正则重命名（regex-rename）：用正则捕获组加模板批量重命名文件。

对目录下的文件名（含扩展名）整体应用一个正则表达式，匹配成功的文件
按模板重命名。模板中 {0} 表示整个匹配，{1}、{2}… 表示第 N 个捕获组，
{ext} 表示原扩展名。支持 --dry-run 预演，不改动任何文件。

用法:
    python regex-rename.py <目录> --pattern "^(.*)_(\\d+)\\.(.*)$" --template "{1}_{2}.{3}" [--dry-run]

示例:
    # 预演：把 photo_001.jpg 改成 001_photo.jpg
    python regex-rename.py ./imgs --pattern "^(\\w+)_(\\d+)\\.(\\w+)$" --template "{2}_{1}.{3}" --dry-run
    # 实际执行（去掉 --dry-run）
    python regex-rename.py ./imgs --pattern "^(\\w+)_(\\d+)\\.(\\w+)$" --template "{2}_{1}.{3}"

只用 Python 标准库。目标名与现有文件或本批其他目标冲突时报错并跳过。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


def _is_same_file(a: Path, b: Path) -> bool:
    """Windows 文件系统大小写不敏感：仅大小写不同的两个路径是同一个文件。"""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="用正则捕获组加模板（如 {1}_{2}）批量重命名文件"
    )
    p.add_argument("directory", help="要处理的目录")
    p.add_argument("--pattern", required=True, help="应用于文件名的正则表达式（可含捕获组）")
    p.add_argument("--template", required=True,
                   help="新文件名模板，支持 {0} 整个匹配、{1}..{n} 捕获组、{ext} 原扩展名")
    p.add_argument("--dry-run", action="store_true", help="只预演，不实际重命名")
    return p


def render(template: str, m: re.Match, original: str) -> str:
    ext = Path(original).suffix.lstrip(".")
    ext_full = Path(original).suffix  # 含点

    def sub(match: re.Match) -> str:
        token = match.group(1)
        if token == "ext":
            return ext_full
        idx = int(token)
        if idx == 0:
            return m.group(0)
        val = m.group(idx)
        if val is None:
            raise ValueError(f"捕获组 {{{idx}}} 未参与匹配")
        return val

    return re.sub(r"\{(\d+|ext)\}", sub, template)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"错误：目录不存在：{directory}", file=sys.stderr)
        return 2
    try:
        rx = re.compile(args.pattern)
    except re.error as e:
        print(f"错误：正则无效：{e}", file=sys.stderr)
        return 2

    files = sorted(p for p in directory.iterdir() if p.is_file())
    if not files:
        print("目录中没有可重命名的文件。")
        return 0

    taken: set[str] = set()
    changed = skipped = 0
    for path in files:
        m = rx.match(path.name)
        if not m:
            continue
        try:
            new_name = render(args.template, m, path.name)
        except (ValueError, IndexError) as e:
            print(f"跳过 {path.name}：{e}", file=sys.stderr)
            skipped += 1
            continue
        if not new_name or new_name == path.name:
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
