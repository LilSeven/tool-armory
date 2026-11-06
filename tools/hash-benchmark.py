#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""哈希算法基准测试 (hash-benchmark)

用途:
    在内存中的随机样例数据 (os.urandom 生成一次并复用) 上, 测量各 hashlib 算法
    的吞吐速度并从高到低排行。吞吐单位 MB/s, 按 1 MB = 1 MiB = 1048576 字节
    计算; 每个算法至少计时 --seconds 秒且至少跑 2 趟后取平均。

示例命令:
    python hash-benchmark.py                              # 默认 32 MiB 样例, 常用算法
    python hash-benchmark.py --size-mb 8 --seconds 0.2
    python hash-benchmark.py --algos md5,sha1,sha256,blake2b

退出码:
    0 = 成功; 2 = 用法错误 (样例大小/时长不合法或算法名不支持)。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time

MIB = 1 << 20
DEFAULT_ALGOS = (
    "md5", "sha1", "sha224", "sha256", "sha384", "sha512",
    "blake2b", "blake2s", "sha3_224", "sha3_256", "sha3_384", "sha3_512",
)


def _setup_stdio() -> None:
    """把标准输出/错误重配为 UTF-8, 避免中文在非 UTF-8 控制台下报编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def make_sample(size_mb: int) -> bytes:
    """生成 size_mb MiB 随机样例数据 (只调用一次 os.urandom, 其余为内存复制)。"""
    block = os.urandom(MIB)
    return block * size_mb


def bench_one(algo: str, data: bytes, min_seconds: float):
    """对单个算法计时, 返回 (平均吞吐 MB/s, 实际用时秒, 处理总字节数)。"""
    hashlib.new(algo, b"warmup")  # 触发实现初始化, 不计入计时
    passes = 0
    total = 0
    start = time.perf_counter()
    while True:
        h = hashlib.new(algo)
        h.update(data)
        h.digest()
        passes += 1
        total += len(data)
        elapsed = time.perf_counter() - start
        if elapsed >= min_seconds and passes >= 2:
            break
    return total / elapsed / MIB, elapsed, total


def main(argv: list[str] | None = None) -> int:
    _setup_stdio()
    parser = argparse.ArgumentParser(
        prog="hash-benchmark",
        description="在样例数据上测量 hashlib 各算法吞吐 (MB/s) 并排行。",
    )
    parser.add_argument("--size-mb", type=int, default=32, metavar="N",
                        help="样例数据大小, 单位 MiB (默认: 32)")
    parser.add_argument("--seconds", type=float, default=0.3, metavar="SEC",
                        help="每个算法的最短计时秒数 (默认: 0.3)")
    parser.add_argument("--algos", metavar="LIST",
                        help="逗号分隔的算法列表 (默认: 全部常用算法)")
    args = parser.parse_args(argv)

    if args.size_mb <= 0 or args.seconds <= 0:
        print("hash-benchmark: --size-mb 与 --seconds 必须为正数", file=sys.stderr)
        return 2

    if args.algos:
        algos = [part.strip().lower() for part in args.algos.split(",") if part.strip()]
    else:
        algos = list(DEFAULT_ALGOS)
    if not algos:
        print("hash-benchmark: --algos 为空", file=sys.stderr)
        return 2
    bad = []
    for algo in algos:
        try:
            hashlib.new(algo)
        except (ValueError, TypeError):
            bad.append(algo)
    if bad:
        print(f"hash-benchmark: 不支持的算法: {', '.join(bad)}", file=sys.stderr)
        print(f"当前可用: {', '.join(sorted(hashlib.algorithms_available))}", file=sys.stderr)
        return 2

    data = make_sample(args.size_mb)
    print(f"样例: {args.size_mb} MiB 随机数据; 每个算法至少计时 {args.seconds:g} 秒; "
          f"单位 MB/s (1 MB = 1048576 字节)")
    rows = []
    for algo in algos:
        speed, elapsed, total = bench_one(algo, data, args.seconds)
        rows.append((algo, speed, elapsed, total))
        print(f"测试 {algo:<10} ... {speed:>10.1f} MB/s", file=sys.stderr)

    rows.sort(key=lambda row: row[1], reverse=True)
    print(f"{'名次':<4}{'算法':<10}{'吞吐 MB/s':>12}{'用时':>9}{'总数据量':>13}")
    for rank, (algo, speed, elapsed, total) in enumerate(rows, 1):
        print(f"{rank:<4}{algo:<10}{speed:>12.1f}{elapsed:>8.2f}s{total / MIB:>11.1f} MiB")
    print(f"最快: {rows[0][0]} ({rows[0][1]:.1f} MB/s); "
          f"最慢: {rows[-1][0]} ({rows[-1][1]:.1f} MB/s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
