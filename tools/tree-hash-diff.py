#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tree-hash-diff.py —— 清单树对比工具（仅用 Python 标准库）。

只比较两个目录的“文件清单”——相对路径、大小、哈希（默认 sha256），
不逐行比较文件内容；哈希一致即视为内容一致。递归子目录，
相对路径一律用 / 分隔，便于跨平台阅读。

报告三类差异:
    - 仅在 A（B 里没有）
    + 仅在 B（A 里没有）
    ~ 大小或哈希不一致（内容视为不同）

示例命令:
    python tree-hash-diff.py dirA dirB
    python tree-hash-diff.py dirA dirB --algo md5
    python tree-hash-diff.py dirA dirB --exclude "*.log" --exclude "tmp/*"

选项:
    --algo NAME     哈希算法（默认 sha256，可用 md5/sha1/sha512 等）
    --exclude PAT   排除规则（fnmatch 通配，匹配相对路径或文件名，可多次给出）
    --max-report N  每类最多列出 N 条（默认 100，0=不限）

退出码:
    0 = 运行成功
    2 = 目录不存在 / 哈希算法不可用
"""

import argparse
import fnmatch
import hashlib
import os
import sys

CHUNK_SIZE = 1 << 16


def setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def hash_file(path, algo):
    try:
        digest = hashlib.new(algo)
    except ValueError:
        return None
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(CHUNK_SIZE), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def scan_tree(root, algo, excludes):
    """遍历目录，返回 {相对路径: {"size": int, "hash": str|None}}。"""
    files = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            if not os.path.isfile(full):
                continue
            rel = os.path.relpath(full, root).replace("\\", "/")
            if any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat)
                   for pat in excludes):
                continue
            try:
                size = os.path.getsize(full)
            except OSError:
                size = -1
            files[rel] = {"size": size, "hash": hash_file(full, algo)}
    return files


def brief(entry):
    digest = entry["hash"]
    hash_text = digest[:12] if digest else "(无法读取)"
    return f"size={entry['size']}, hash={hash_text}"


def main(argv=None):
    setup_stdio()
    parser = argparse.ArgumentParser(
        description="只比较两目录的文件清单（存在性、大小、哈希），不逐行比内容。")
    parser.add_argument("dir_a", help="目录 A（旧）")
    parser.add_argument("dir_b", help="目录 B（新）")
    parser.add_argument("--algo", default="sha256",
                        help="哈希算法（默认 sha256）")
    parser.add_argument("--exclude", action="append", default=[],
                        help="排除规则（fnmatch 通配，可多次给出）")
    parser.add_argument("--max-report", type=int, default=100,
                        help="每类最多列出 N 条（0=不限，默认 100）")
    args = parser.parse_args(argv)

    for label, path in (("A", args.dir_a), ("B", args.dir_b)):
        if not os.path.isdir(path):
            print(f"错误: 目录不存在或不是目录: {label}: {path}", file=sys.stderr)
            return 2
    try:
        hashlib.new(args.algo)
    except ValueError:
        print(f"错误: 未知哈希算法: {args.algo}", file=sys.stderr)
        return 2

    tree_a = scan_tree(args.dir_a, args.algo, args.exclude)
    tree_b = scan_tree(args.dir_b, args.algo, args.exclude)

    only_a = sorted(set(tree_a) - set(tree_b))
    only_b = sorted(set(tree_b) - set(tree_a))
    changed = sorted(
        rel for rel in set(tree_a) & set(tree_b)
        if tree_a[rel]["size"] != tree_b[rel]["size"]
        or tree_a[rel]["hash"] != tree_b[rel]["hash"])

    groups = [
        ("仅在 A", [f"- 仅在 A: {rel}  ({brief(tree_a[rel])})"
                    for rel in only_a]),
        ("仅在 B", [f"+ 仅在 B: {rel}  ({brief(tree_b[rel])})"
                    for rel in only_b]),
        ("大小或哈希不一致", [f"~ 不一致: {rel}  "
                             f"A[{brief(tree_a[rel])}] -> B[{brief(tree_b[rel])}]"
                             for rel in changed]),
    ]
    for label, lines in groups:
        cap = len(lines) if args.max_report == 0 else args.max_report
        for line in lines[:cap]:
            print(line)
        if len(lines) > cap:
            print(f"  ...（{label}还有 {len(lines) - cap} 条未显示）")

    if not (only_a or only_b or changed):
        print(f"两目录文件清单一致（共 {len(tree_a)} 个文件，算法 {args.algo}）。")
    else:
        print(f"摘要: 仅在A {len(only_a)} 个, 仅在B {len(only_b)} 个, "
              f"不一致 {len(changed)} 个"
              f"（A 共 {len(tree_a)} 个文件, B 共 {len(tree_b)} 个, "
              f"算法 {args.algo}）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
