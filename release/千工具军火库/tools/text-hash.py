#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文本多算法哈希：对同一段文本同时计算多种哈希并对齐列表输出。

文本按 UTF-8 编码后计算。默认算法（按当前 Python 的 hashlib 实际支持裁剪）:
md5, sha1, sha224, sha256, sha384, sha512, sha3_224, sha3_256, sha3_384,
sha3_512, blake2b, blake2s。

用法:
    python text-hash.py [文本]
    python text-hash.py --algo md5,sha256 'hello'
    printf 'hello' | python text-hash.py      # 注意: echo 自带换行会改变哈希值
    python text-hash.py -s < 文件             # -s/--strip: 去掉 stdin 末尾一个换行

示例:
    $ printf 'hello' | python text-hash.py --algo md5,sha1,sha256
    md5     5d41402abc4b2a76b9719d911017c592
    sha1    aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d
    sha256  2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
"""

from __future__ import annotations

import argparse
import hashlib
import sys

DEFAULT_ALGOS = (
    "md5", "sha1", "sha224", "sha256", "sha384", "sha512",
    "sha3_224", "sha3_256", "sha3_384", "sha3_512",
    "blake2b", "blake2s",
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="对一段文本同时计算 md5/sha1/sha256/sha512/blake2 等哈希并列表输出",
    )
    parser.add_argument("text", nargs="?", default=None,
                        help="待哈希文本；省略时从 stdin 读取")
    parser.add_argument("-a", "--algo", default=None,
                        help="逗号分隔的算法名(如 md5,sha256)；默认全部支持列表")
    parser.add_argument("-s", "--strip", action="store_true",
                        help="去掉输入末尾一个换行再计算")
    parser.add_argument("-u", "--upper", action="store_true",
                        help="十六进制摘要大写输出")
    args = parser.parse_args(argv)

    text = args.text
    if text is None:
        if sys.stdin.isatty():
            parser.error("未提供文本：请用参数传入，或通过管道从 stdin 读取")
        text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    if args.strip and text.endswith("\n"):
        text = text[:-1]
        if text.endswith("\r"):
            text = text[:-1]

    data = text.encode("utf-8")

    if args.algo:
        names = [n.strip().lower() for n in args.algo.split(",") if n.strip()]
    else:
        names = list(DEFAULT_ALGOS)

    algos, skipped = [], []
    for name in names:
        try:
            hashlib.new(name)
        except (ValueError, TypeError):
            skipped.append(name)
        else:
            algos.append(name)
    if skipped:
        print(f"警告: 当前 Python 不支持或名称无效，已跳过: {', '.join(skipped)}",
              file=sys.stderr)
    if not algos:
        print("错误: 没有可用的哈希算法", file=sys.stderr)
        return 1

    width = max(len(name) for name in algos)
    for name in algos:
        digest = hashlib.new(name, data).hexdigest()
        if args.upper:
            digest = digest.upper()
        print(f"{name.ljust(width)}  {digest}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
