#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件哈希计算 (file-hash)

用途:
    对一个或多个文件计算指定算法的哈希, 按 GNU coreutils 风格输出标准 hashsum
    行 "<哈希值>  <文件路径>" (哈希与路径之间两个空格, 可直接交给 sha256sum -c
    或同目录的 hash-verify.py 核对); --tag 输出 BSD 风格 "SHA256 (文件) = 哈希" 行。
    文件按 1 MiB 分块流式读取, 支持大文件。

示例命令:
    python file-hash.py a.txt b.txt
    python file-hash.py -a md5 data.bin
    python file-hash.py -a sha1 --tag notes.txt
    python file-hash.py -                       # 从标准输入读取, 输出行中路径显示为 -

说明:
    算法为 hashlib.new() 支持的任意名称 (md5/sha1/sha224/sha256/sha384/sha512/
    blake2b/blake2s/sha3_* ...), 默认 sha256。

退出码:
    0 = 全部计算成功; 1 = 有文件打开或读取失败; 2 = 用法错误或算法名不支持。
"""

from __future__ import annotations

import argparse
import hashlib
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


def hash_stdin(algo: str) -> str:
    """从标准输入流式读取并计算哈希。"""
    h = hashlib.new(algo)
    for block in iter(lambda: sys.stdin.buffer.read(CHUNK_SIZE), b""):
        h.update(block)
    return h.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="file-hash",
        description="对文件计算哈希, 输出 GNU hashsum 行格式: 哈希值  文件路径。",
    )
    parser.add_argument("files", nargs="+", metavar="FILE",
                        help="要计算哈希的文件, 可给多个; '-' 表示标准输入")
    parser.add_argument("-a", "--algorithm", default="sha256", metavar="ALGO",
                        help="哈希算法 (默认: sha256, 如 md5/sha1/blake2b)")
    parser.add_argument("--tag", action="store_true",
                        help="输出 BSD 风格行: SHA256 (文件) = 哈希")
    return parser


def main(argv: list[str] | None = None) -> int:
    _setup_stdio()
    args = build_parser().parse_args(argv)

    algo = args.algorithm.lower()
    try:
        hashlib.new(algo)
    except (ValueError, TypeError):
        print(f"file-hash: 不支持的算法: {args.algorithm}", file=sys.stderr)
        return 2

    failed = 0
    for path in args.files:
        try:
            digest = hash_stdin(algo) if path == "-" else hash_file(path, algo)
        except OSError as exc:
            failed += 1
            print(f"file-hash: {path}: {exc.strerror or exc}", file=sys.stderr)
            continue
        if args.tag:
            print(f"{algo.upper().replace('_', '-')} ({path}) = {digest}")
        else:
            print(f"{digest}  {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
