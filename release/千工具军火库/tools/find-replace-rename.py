#!/usr/bin/env python3
"""查找替换重命名（find-replace-rename）：对文件名做字面字符串替换。

把文件名中的字面子串（如「最终版」）替换为指定文字（如 v2），
支持 --ignore-case 忽略大小写、--first-only 仅替换首次出现。
支持 --dry-run 预演。

用法:
    python find-replace-rename.py <目录> --find 原 --replace 新 [--ignore-case] [--first-only] [--dry-run]

示例:
    # 预演：把「最终版」换成 v2
    python find-replace-rename.py ./docs --find 最终版 --replace v2 --dry-run
    # 实际执行：忽略大小写地替换第一个 Old
    python find-replace-rename.py ./docs --find Old --replace New --ignore-case --first-only

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


def replace_once(s: str, old: str, new: str) -> str:
    idx = s.lower().find(old.lower())
    if idx == -1:
        return s
    return s[:idx] + new + s[idx + len(old):]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="对文件名做字面字符串替换（如把「最终版」换成 v2）")
    p.add_argument("directory", help="要处理的目录")
    p.add_argument("--find", required=True, help="要查找的字面字符串")
    p.add_argument("--replace", required=True, help="替换为的字面字符串")
    p.add_argument("--ignore-case", action="store_true", help="查找时忽略大小写")
    p.add_argument("--first-only", action="store_true", help="仅替换首次出现")
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
        name = path.name
        if args.ignore_case:
            # 忽略大小写匹配，但保留原文其余部分的大小写
            if args.first_only:
                new_name = replace_once(name, args.find, args.replace)
            else:
                new_name = _replace_all_case(name, args.find, args.replace)
        else:
            new_name = name.replace(args.find, args.replace, 1 if args.first_only else -1)
        if new_name == name or not new_name:
            continue
        candidate = directory / new_name
        if candidate.exists() and not _is_same_file(candidate, path):
            print(f"跳过 {path.name}：目标名已存在 -> {new_name}", file=sys.stderr)
            skipped += 1
            continue
        taken.add(new_name.lower())
        action = "预演" if args.dry_run else "重命名"
        print(f"{action}: {name} -> {new_name}")
        if not args.dry_run:
            try:
                path.rename(directory / new_name)
            except OSError as e:
                print(f"失败 {name}：{e}", file=sys.stderr)
                skipped += 1
                continue
        changed += 1

    print(f"完成：{'预演' if args.dry_run else '实际'}重命名 {changed} 个文件，跳过 {skipped} 个。")
    return 0


def _replace_all_case(name: str, old: str, new: str) -> str:
    """忽略大小写替换所有出现，保留原文其余部分的大小写。"""
    out = []
    low, o = name.lower(), old.lower()
    i = 0
    while True:
        j = low.find(o, i)
        if j == -1:
            out.append(name[i:])
            break
        out.append(name[i:j])
        out.append(new)
        i = j + len(o)
    return "".join(out)


if __name__ == "__main__":
    sys.exit(main())
