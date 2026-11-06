#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""目录树哈希清单 (dir-checksum)

用途:
    1) 递归扫描目录, 为其中所有文件生成 "相对路径 + 哈希" 清单, 输出 GNU hashsum
       行格式 (相对路径统一以 / 分隔并按字典序排序, 可直接交给 sha256sum -c 或
       同目录的 hash-verify.py 核对);
    2) 给定两个目录时, 对比两份清单, 找出仅存在于一侧、或相对路径相同但内容
       (哈希) 不同的文件。

示例命令:
    python dir-checksum.py D:/proj                      # 清单输出到标准输出
    python dir-checksum.py D:/proj -a md5 -o m.md5      # 清单写入文件
    python dir-checksum.py D:/projA D:/projB            # 对比两个目录
    python dir-checksum.py D:/proj --exclude "*.log" --exclude ".git/*"

退出码:
    0 = 清单生成成功, 或两个目录的文件集合与内容完全一致;
    1 = 两个目录存在差异 (仅一侧存在或哈希不同);
    2 = 目录不存在、文件读取失败或用法错误。
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import os
import sys

CHUNK_SIZE = 1 << 20  # 1 MiB


def _setup_stdio() -> None:
    """把标准输出/错误重配为 UTF-8, 避免中文在非 UTF-8 控制台下报编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def hash_file(path: str, algo: str) -> str:
    """流式计算单个文件的十六进制哈希; 打开/读取失败时抛出 OSError。"""
    h = hashlib.new(algo)
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK_SIZE), b""):
            h.update(block)
    return h.hexdigest()


def scan_tree(root: str, algo: str, excludes: list[str]):
    """递归扫描 root, 返回 ({相对路径: 哈希}, [(相对路径, 错误消息)])。

    相对路径以 '/' 分隔; excludes 为 fnmatch 模式, 匹配相对路径或文件名。
    """
    root_abs = os.path.abspath(root)
    hashes: dict[str, str] = {}
    errors: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root_abs):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root_abs).replace(os.sep, "/")
            if any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat)
                   for pat in excludes):
                continue
            try:
                hashes[rel] = hash_file(full, algo)
            except OSError as exc:
                errors.append((rel, exc.strerror or str(exc)))
    return hashes, errors


def write_manifest(hashes: dict[str, str], out_fh) -> None:
    """按 "<哈希>  <相对路径>" 输出 (哈希与路径间两个空格, GNU 文本模式)。"""
    for rel in sorted(hashes):
        out_fh.write(f"{hashes[rel]}  {rel}\n")


def main(argv: list[str] | None = None) -> int:
    _setup_stdio()
    parser = argparse.ArgumentParser(
        prog="dir-checksum",
        description="递归生成目录的相对路径+哈希清单; 给两个目录则对比差异。",
    )
    parser.add_argument("dirs", nargs="+", metavar="DIR",
                        help="一个目录 (生成清单) 或两个目录 (对比差异)")
    parser.add_argument("-a", "--algorithm", default="sha256", metavar="ALGO",
                        help="哈希算法 (默认: sha256)")
    parser.add_argument("-o", "--output", metavar="FILE",
                        help="把清单写入文件 (仅单目录模式; 默认输出到标准输出)")
    parser.add_argument("--exclude", action="append", default=[], metavar="PATTERN",
                        help="排除匹配的文件名或相对路径 (fnmatch 通配, 可多次)")
    args = parser.parse_args(argv)

    algo = args.algorithm.lower()
    try:
        hashlib.new(algo)
    except (ValueError, TypeError):
        print(f"dir-checksum: 不支持的算法: {args.algorithm}", file=sys.stderr)
        return 2

    if len(args.dirs) not in (1, 2):
        print("dir-checksum: 需要 1 个目录 (生成清单) 或 2 个目录 (对比差异)",
              file=sys.stderr)
        return 2
    if args.output and len(args.dirs) == 2:
        print("dir-checksum: -o/--output 仅支持单目录清单模式", file=sys.stderr)
        return 2

    if len(args.dirs) == 1:
        root = args.dirs[0]
        if not os.path.isdir(root):
            print(f"dir-checksum: 目录不存在: {root}", file=sys.stderr)
            return 2
        hashes, errors = scan_tree(root, algo, args.exclude)
        if args.output:
            with open(args.output, "w", encoding="utf-8", newline="\n") as out_fh:
                write_manifest(hashes, out_fh)
            print(f"已写出 {len(hashes)} 条到 {args.output} ({algo})", file=sys.stderr)
        else:
            write_manifest(hashes, sys.stdout)
        for rel, msg in errors:
            print(f"dir-checksum: {rel}: {msg}", file=sys.stderr)
        return 2 if errors else 0

    dir_a, dir_b = args.dirs
    for d in (dir_a, dir_b):
        if not os.path.isdir(d):
            print(f"dir-checksum: 目录不存在: {d}", file=sys.stderr)
            return 2
    map_a, errors_a = scan_tree(dir_a, algo, args.exclude)
    map_b, errors_b = scan_tree(dir_b, algo, args.exclude)

    only_a = sorted(map_a.keys() - map_b.keys())
    only_b = sorted(map_b.keys() - map_a.keys())
    common = map_a.keys() & map_b.keys()
    different = sorted(rel for rel in common if map_a[rel] != map_b[rel])
    same_count = len(common) - len(different)

    print(f"对比: {dir_a}  <->  {dir_b}")
    print(f"仅存在于第一个目录: {len(only_a)} 个")
    for rel in only_a:
        print(f"  < {rel}")
    print(f"仅存在于第二个目录: {len(only_b)} 个")
    for rel in only_b:
        print(f"  > {rel}")
    print(f"内容不同 (哈希不一致): {len(different)} 个")
    for rel in different:
        print(f"  ! {rel}")
    print(f"内容一致: {same_count} 个")
    for rel, msg in errors_a + errors_b:
        print(f"dir-checksum: {rel}: {msg}", file=sys.stderr)
    if errors_a or errors_b:
        return 2
    return 1 if (only_a or only_b or different) else 0


if __name__ == "__main__":
    sys.exit(main())
