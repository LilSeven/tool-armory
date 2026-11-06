#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件相同性比较 (file-compare-hash)

用途:
    比较两个文件是否完全一致, 快速给出结论:
      1. 先比较文件大小 (os.path.getsize), 大小不同立即判定不同, 不读文件内容;
      2. 大小相同再按固定块大小 (默认 1 MiB) 逐块计算哈希并对比, 遇到第一个
         不一致的块提前结束; 全部块一致且整体哈希一致则判定完全一致。

示例命令:
    python file-compare-hash.py a.bin b.bin
    python file-compare-hash.py --chunk-size 65536 a.bin b.bin
    python file-compare-hash.py -a md5 big1.iso big2.iso

退出码:
    0 = 完全一致; 1 = 不一致 (大小或哈希不同); 2 = 文件打开/读取失败或用法错误。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys

DEFAULT_CHUNK = 1 << 20  # 1 MiB


def _setup_stdio() -> None:
    """把标准输出/错误重配为 UTF-8, 避免中文在非 UTF-8 控制台下报编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def compare_files(path_a: str, path_b: str, algo: str, chunk_size: int) -> dict:
    """比较两个文件, 返回带 verdict 的结果字典; 文件错误抛 OSError。

    verdict 取值: "size" (大小不同) / "chunk" (分块哈希不同) / "same" (一致)。
    """
    size_a = os.path.getsize(path_a)
    size_b = os.path.getsize(path_b)
    if size_a != size_b:
        return {"verdict": "size", "size_a": size_a, "size_b": size_b}

    total_a = hashlib.new(algo)
    total_b = hashlib.new(algo)
    chunks = 0
    with open(path_a, "rb") as fa, open(path_b, "rb") as fb:
        while True:
            block_a = fa.read(chunk_size)
            block_b = fb.read(chunk_size)
            if not block_a and not block_b:
                break
            if hashlib.new(algo, block_a).digest() != hashlib.new(algo, block_b).digest():
                return {"verdict": "chunk", "size": size_a, "chunks": chunks + 1,
                        "chunk_index": chunks + 1}
            total_a.update(block_a)
            total_b.update(block_b)
            chunks += 1
    if total_a.hexdigest() != total_b.hexdigest():  # 理论上不会发生, 防御性兜底
        return {"verdict": "chunk", "size": size_a, "chunks": chunks, "chunk_index": None}
    return {"verdict": "same", "size": size_a, "chunks": chunks,
            "digest": total_a.hexdigest()}


def main(argv: list[str] | None = None) -> int:
    _setup_stdio()
    parser = argparse.ArgumentParser(
        prog="file-compare-hash",
        description="先比大小、再比分块哈希, 快速判断两个文件是否完全一致。",
    )
    parser.add_argument("file_a", metavar="FILE1", help="第一个文件")
    parser.add_argument("file_b", metavar="FILE2", help="第二个文件")
    parser.add_argument("-a", "--algorithm", default="sha256", metavar="ALGO",
                        help="哈希算法 (默认: sha256)")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK, metavar="BYTES",
                        help=f"分块大小字节数 (默认: {DEFAULT_CHUNK})")
    args = parser.parse_args(argv)

    algo = args.algorithm.lower()
    try:
        hashlib.new(algo)
    except (ValueError, TypeError):
        print(f"file-compare-hash: 不支持的算法: {args.algorithm}", file=sys.stderr)
        return 2
    if args.chunk_size <= 0:
        print("file-compare-hash: --chunk-size 必须为正整数", file=sys.stderr)
        return 2

    try:
        result = compare_files(args.file_a, args.file_b, algo, args.chunk_size)
    except OSError as exc:
        print(f"file-compare-hash: {exc.filename or ''}: {exc.strerror or exc}",
              file=sys.stderr)
        return 2

    if result["verdict"] == "size":
        print(f"结论: 不同 —— 文件大小不一致 "
              f"({args.file_a} = {result['size_a']} 字节, "
              f"{args.file_b} = {result['size_b']} 字节)")
        return 1
    if result["verdict"] == "chunk":
        if result["chunk_index"]:
            detail = (f"分块哈希在第 {result['chunk_index']} 块不一致 "
                      f"(比较到第 {result['chunks']} 块提前结束, 每块 {args.chunk_size} 字节)")
        else:
            detail = "整体哈希不一致"
        print(f"结论: 不同 —— {detail}")
        return 1
    print(f"结论: 完全一致 —— 大小 {result['size']} 字节, 比较 {result['chunks']} 块, "
          f"{algo} = {result['digest']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
