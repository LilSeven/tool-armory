#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nanoid-tool.py -- 纯 Python 标准库实现的 NanoID 短随机 ID 生成器。

用途:
    生成与 UUID-4 等安全强度、但更短且 URL 友好的随机 ID。默认
    21 个字符、64 字符字母表(约 126 bit 熵); 可用 --size 调整长度,
    --alphabet 换用自定义字母表(字符须唯一)。随机源为标准库
    secrets(os.urandom), 并按 NanoID 规范做拒绝采样(rejection
    sampling), 保证每个字符出现概率均匀无偏。

用法:
    python -I nanoid-tool.py                          # 生成 1 个 21 位默认 NanoID
    python -I nanoid-tool.py --size 10 --count 5      # 生成 5 个 10 位 ID
    python -I nanoid-tool.py --alphabet ABC123 --size 8

示例:
    $ python -I nanoid-tool.py
    V1StGXR8_Z5jdHi6B-myT
    $ python -I nanoid-tool.py --size 8 --alphabet 0123456789
    73019482
"""

import argparse
import math
import secrets
import sys

DEFAULT_ALPHABET = ("ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                    "abcdefghijklmnopqrstuvwxyz"
                    "0123456789_-")


def generate(size, alphabet):
    """Return one NanoID of `size` chars drawn from `alphabet`.

    Follows the NanoID spec: compute the smallest bit mask covering the
    alphabet index range, request random bytes in bulk
    (step = ceil(1.6 * mask * size / n)) and reject draws >= n, so every
    character is uniformly distributed even when the alphabet size is
    not a power of two.
    """
    n = len(alphabet)
    if n == 0:
        raise ValueError("alphabet must not be empty")
    if len(set(alphabet)) != n:
        raise ValueError("alphabet contains duplicate characters")
    if size < 1:
        raise ValueError("size must be a positive integer")

    mask = 1
    while mask < n - 1:
        mask = (mask << 1) | 1
    step = int(math.ceil(1.6 * mask * size / n))

    out = []
    while len(out) < size:
        for b in secrets.token_bytes(step):
            idx = b & mask
            if idx < n:
                out.append(alphabet[idx])
                if len(out) == size:
                    break
    return "".join(out)


def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="nanoid-tool.py",
        description="Generate short random IDs (NanoID) using only the Python standard library.")
    parser.add_argument("-s", "--size", type=int, default=21,
                        help="ID length in characters (default: 21)")
    parser.add_argument("-a", "--alphabet", default=DEFAULT_ALPHABET,
                        help="characters to draw from, all unique (default: URL-safe 64-char set)")
    parser.add_argument("-c", "--count", type=int, default=1,
                        help="how many IDs to generate (default: 1)")
    args = parser.parse_args(argv)

    try:
        ids = [generate(args.size, args.alphabet) for _ in range(max(args.count, 0))]
    except ValueError as exc:
        parser.error(str(exc))
    for i in ids:
        print(i)
    return 0


if __name__ == "__main__":
    _utf8_stdio()
    sys.exit(main())
