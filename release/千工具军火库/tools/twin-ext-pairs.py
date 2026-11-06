#!/usr/bin/env python3
"""twin-ext-pairs —— 同名多扩展文件对查找器。

在目录中找出"主名相同、扩展名不同"的成对文件（如 photo.jpg 与 photo.RAW），
并列出缺少同伴的孤儿文件（其主名只出现一种扩展名）。
适合照片+RAW、文档+备份 等成对文件场景的完整性检查。

用法:
    python twin-ext-pairs.py <目录> [选项]

选项:
    -r, --recursive     递归扫描子目录（各子目录内分别配对）
    --exts LIST         只考虑这些扩展名，逗号分隔，点号可省略，如 jpg,raw,cr2
    --json              以 JSON 格式输出结果

示例:
    python twin-ext-pairs.py D:/photos -r
    python twin-ext-pairs.py D:/photos -r --exts jpg,jpeg,raw,cr2,nef
    python twin-ext-pairs.py D:/photos -r --json

退出码: 0 = 运行成功（有无配对不影响退出码）；2 = 目录不存在等用法错误。
仅使用 Python 标准库。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def iter_files(root: str, recursive: bool):
    if recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for name in sorted(filenames):
                yield os.path.join(dirpath, name)
    else:
        try:
            with os.scandir(root) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as exc:
            print(f"警告: 无法读取目录 {root}: {exc}", file=sys.stderr)
            return
        for entry in entries:
            if entry.is_file():
                yield entry.path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="twin-ext-pairs",
        description="找出主名相同但扩展名不同的成对文件，并列出缺少同伴的孤儿文件。",
    )
    parser.add_argument("root", help="要扫描的目录")
    parser.add_argument("-r", "--recursive", action="store_true", help="递归扫描子目录")
    parser.add_argument("--exts", default="", metavar="JPG,RAW",
                        help="只考虑这些扩展名（逗号分隔，点号可省略）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args(argv)

    root = args.root
    if not os.path.isdir(root):
        print(f"错误: 不是目录或不存在: {root}", file=sys.stderr)
        return 2

    ext_filter = None
    if args.exts.strip():
        ext_filter = set()
        for token in args.exts.split(","):
            token = token.strip().lower()
            if token:
                ext_filter.add(token if token.startswith(".") else "." + token)

    groups: dict = defaultdict(list)  # (相对目录, 小写主名) -> [文件路径]
    for path in iter_files(root, args.recursive):
        stem, ext = os.path.splitext(os.path.basename(path))
        if ext_filter is not None and ext.lower() not in ext_filter:
            continue
        rel_dir = os.path.relpath(os.path.dirname(path), root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace("\\", "/")
        groups[(rel_dir, stem.lower())].append(path)

    pairs, orphans = [], []
    for (rel_dir, _stem), paths in groups.items():
        if len(paths) >= 2:
            pairs.append((rel_dir, sorted(paths)))
        else:
            orphans.append((rel_dir, paths[0]))
    pairs.sort(key=lambda item: (item[0], item[1]))
    orphans.sort()

    if args.json:
        payload = {
            "root": root,
            "pair_count": len(pairs),
            "orphan_count": len(orphans),
            "pairs": [
                {
                    "dir": rel_dir or ".",
                    "stem": os.path.splitext(os.path.basename(paths[0]))[0],
                    "files": paths,
                }
                for rel_dir, paths in pairs
            ],
            "orphans": [
                {"dir": rel_dir or ".", "file": path} for rel_dir, path in orphans
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not pairs and not orphans:
        print("（目录下没有符合条件的文件）")
        return 0
    if pairs:
        print(f"成对文件 {len(pairs)} 组（主名相同、扩展名不同）:")
        for rel_dir, paths in pairs:
            names = " + ".join(os.path.basename(p) for p in paths)
            prefix = f"  [{rel_dir}] " if rel_dir else "  "
            print(f"{prefix}{names}")
        print()
    if orphans:
        print(f"孤儿文件 {len(orphans)} 个（缺少同名同伴）:")
        for rel_dir, path in orphans:
            prefix = f"  [{rel_dir}] " if rel_dir else "  "
            print(f"{prefix}{os.path.basename(path)}")
    return 0


if __name__ == "__main__":
    _force_utf8_stdio()
    sys.exit(main())
