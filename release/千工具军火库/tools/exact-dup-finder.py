#!/usr/bin/env python3
"""精确重复文件查找器（两遍法）：先按大小分组，再对同大小文件算全量哈希。

第一遍递归扫描所有文件并按文件大小分组——大小不同内容必不同；第二遍只对
大小相同的文件计算全量哈希（默认 SHA-256，1 MiB 分块读取），哈希一致即视为
内容完全相同，按组输出并汇总可释放空间。不跟随符号链接；读取失败的文件
警告后跳过。

示例：
  python exact-dup-finder.py D:/downloads
  python exact-dup-finder.py a b --hash md5 --min-size 1024
  python exact-dup-finder.py . -H

退出码：0 正常（未发现重复也是 0）；1 有读取警告；2 路径不存在。
"""

import argparse
import hashlib
import os
import sys

CHUNK = 1 << 20
ALGOS = ("md5", "sha1", "sha256", "sha512", "blake2b")
UNITS = ("B", "KiB", "MiB", "GiB", "TiB")


def human(n: float) -> str:
    n = float(n)
    for i, unit in enumerate(UNITS):
        if n < 1024 or i == len(UNITS) - 1:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}{UNITS[-1]}"


def digest_of(path: str, algo: str) -> str:
    """全量哈希：分块读取整个文件。"""
    h = hashlib.new(algo)
    with open(path, "rb") as fh:
        while True:
            block = fh.read(CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


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
                files.append((entry.stat(follow_symlinks=False).st_size, entry.path))
        except OSError as exc:
            errors.append(f"无法访问 {entry.path}: {exc}")


def collect_files(roots, errors: list) -> list:
    """返回 [(size, path), ...]。"""
    files = []
    for root in roots:
        if os.path.islink(root):
            continue
        if os.path.isfile(root):
            try:
                files.append((os.path.getsize(root), root))
            except OSError as exc:
                errors.append(f"无法访问 {root}: {exc}")
        elif os.path.isdir(root):
            walk_files(root, files, errors)
        else:
            errors.append(f"路径不存在: {root}")
    return files


def print_groups(groups: list, algo: str, human_flag: bool) -> None:
    for size, digest, paths in groups:
        size_text = human(size) if human_flag else f"{size} 字节"
        print(f"== {size_text} × {len(paths)}  {algo}={digest[:12]}")
        for p in paths:
            print(f"  {p}")


def main(argv=None) -> int:
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        prog="exact-dup-finder",
        description="两遍法（先比大小再算哈希）找出内容完全相同的文件并按组输出。",
    )
    parser.add_argument("roots", nargs="*", help="要扫描的目录或文件（默认当前目录）")
    parser.add_argument("--hash", choices=ALGOS, default="sha256", help="哈希算法（默认 sha256）")
    parser.add_argument("--min-size", type=int, default=1, metavar="N",
                        help="忽略小于 N 字节的文件（默认 1）")
    parser.add_argument("-H", "--human", action="store_true", help="人类可读大小（默认字节）")
    args = parser.parse_args(argv)

    roots = args.roots or ["."]
    errors: list = []
    valid = [r for r in roots if os.path.isdir(r) or os.path.isfile(r)]
    for r in roots:
        if r not in valid:
            errors.append(f"路径不存在: {r}")
    if not valid:
        for msg in errors:
            print(f"错误: {msg}", file=sys.stderr)
        return 2

    # 第一遍：按大小分组，大小不同的组直接丢弃
    files = collect_files(valid, errors)
    by_size: dict = {}
    for size, path in files:
        if size >= args.min_size:
            by_size.setdefault(size, []).append(path)
    candidates = {s: p for s, p in by_size.items() if len(p) > 1}

    # 第二遍：只对大小相同的文件计算全量哈希
    groups = []
    for size in sorted(candidates, reverse=True):
        by_hash: dict = {}
        for path in sorted(candidates[size]):
            try:
                d = digest_of(path, args.hash)
            except OSError as exc:
                errors.append(f"无法读取 {path}: {exc}")
                continue
            by_hash.setdefault(d, []).append(path)
        for d in sorted(by_hash):
            paths = by_hash[d]
            if len(paths) > 1:
                groups.append((size, d, paths))

    print_groups(groups, args.hash, args.human)
    extra = sum(len(p) - 1 for _, _, p in groups)
    wasted = sum(size * (len(p) - 1) for size, _, p in groups)
    if groups:
        waste_text = human(wasted) if args.human else f"{wasted} 字节"
        print(f"发现 {len(groups)} 组重复文件：{extra} 个多余副本，共可释放 {waste_text}")
    else:
        print("未发现重复文件")
    for msg in errors:
        print(f"警告: {msg}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
