#!/usr/bin/env python3
"""快速重复文件扫描器：大小 → 首块哈希 → 全量哈希 三级过滤。

大目录里"大小相同"的文件远多于真正重复的文件。本工具按三级过滤逐步缩小
候选集：① 按文件大小分组（大小不同内容必不同）；② 对同组文件只读取开头
--block 字节计算哈希，首块不同则内容必不同，直接排除；③ 仅对首块也相同
的文件做全量哈希确认。输出与 exact-dup-finder 相同格式的重复组，并在
stderr 打印三级过滤统计（含省去的全量哈希次数）。不跟随符号链接。

示例：
  python fast-dup-partial-hash.py D:/bigdata
  python fast-dup-partial-hash.py D:/bigdata --block 512 --hash blake2b
  python fast-dup-partial-hash.py a b --min-size 1048576 -H

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


def digest_of(path: str, algo: str, limit=None) -> str:
    """计算哈希；limit 给定时只读文件前 limit 字节（首块哈希）。"""
    h = hashlib.new(algo)
    with open(path, "rb") as fh:
        if limit is None:
            while True:
                block = fh.read(CHUNK)
                if not block:
                    break
                h.update(block)
        else:
            h.update(fh.read(limit))
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
        prog="fast-dup-partial-hash",
        description="大小→首块哈希→全量哈希三级过滤，在大目录中高速定位重复文件。",
    )
    parser.add_argument("roots", nargs="*", help="要扫描的目录或文件（默认当前目录）")
    parser.add_argument("--block", type=int, default=65536, metavar="N",
                        help="首块哈希读取的字节数（默认 65536）")
    parser.add_argument("--hash", choices=ALGOS, default="sha256", help="哈希算法（默认 sha256）")
    parser.add_argument("--min-size", type=int, default=1, metavar="N",
                        help="忽略小于 N 字节的文件（默认 1）")
    parser.add_argument("-H", "--human", action="store_true", help="人类可读大小（默认字节）")
    args = parser.parse_args(argv)
    if args.block < 1:
        parser.error("--block 必须 >= 1")

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

    # 第一级：按文件大小分组
    files = collect_files(valid, errors)
    by_size: dict = {}
    for size, path in files:
        if size >= args.min_size:
            by_size.setdefault(size, []).append(path)
    candidates = {s: p for s, p in by_size.items() if len(p) > 1}

    n_partial = n_full = 0
    groups = []
    for size in sorted(candidates, reverse=True):
        # 第二级：首块哈希——首块不同则内容必不同
        by_first: dict = {}
        for path in sorted(candidates[size]):
            try:
                d = digest_of(path, args.hash, limit=args.block)
                n_partial += 1
            except OSError as exc:
                errors.append(f"无法读取 {path}: {exc}")
                continue
            by_first.setdefault(d, []).append(path)
        for d in sorted(by_first):
            first_group = by_first[d]
            if len(first_group) < 2:
                continue  # 首块不同 => 内容不同，省去全量哈希
            # 第三级：全量哈希确认
            by_full: dict = {}
            for path in first_group:
                try:
                    df = digest_of(path, args.hash)
                    n_full += 1
                except OSError as exc:
                    errors.append(f"无法读取 {path}: {exc}")
                    continue
                by_full.setdefault(df, []).append(path)
            for df in sorted(by_full):
                dup_paths = by_full[df]
                if len(dup_paths) > 1:
                    groups.append((size, df, dup_paths))

    print_groups(groups, args.hash, args.human)
    extra = sum(len(p) - 1 for _, _, p in groups)
    wasted = sum(size * (len(p) - 1) for size, _, p in groups)
    if groups:
        print(f"发现 {len(groups)} 组重复文件：{extra} 个多余副本，共可释放 {wasted} 字节")
    else:
        print("未发现重复文件")
    print(f"[统计] 扫描文件 {len(files)} | 大小候选 {sum(len(p) for p in candidates.values())} | "
          f"首块哈希 {n_partial} | 全量哈希 {n_full} | 重复组 {len(groups)} | 冗余副本 {extra} | "
          f"可释放 {wasted} 字节 | 省去全量哈希 {n_partial - n_full} 次",
          file=sys.stderr)
    for msg in errors:
        print(f"警告: {msg}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
