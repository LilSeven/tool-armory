#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验和清单核对 (hash-verify)

用途:
    读取 sha256sum/md5sum 格式的校验和清单文件, 逐个核对本地文件完整性并报告。
    兼容 GNU coreutils 行格式 "<哈希> [空格|*]<文件名>" (如 "abc123...  a.txt"),
    支持以 '\\' 开头的转义行和以 '#' 开头的注释行, 兼容 CRLF。
    算法按哈希长度自动识别 (32=md5, 40=sha1, 56=sha224, 64=sha256, 96=sha384,
    128=sha512), 也可用 -a 强制指定。清单中的相对路径默认相对于清单文件所在
    目录解析 (可用 --base 覆盖)。

示例命令:
    python hash-verify.py checksums.txt
    python hash-verify.py -a md5 md5sums.txt
    python hash-verify.py sums.txt --base D:/data --quiet

退出码:
    0 = 全部核对通过; 1 = 有文件校验和不匹配, 或清单中没有任何有效条目;
    2 = 有文件无法打开/读取, 或清单行无法解析/清单不可读。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys

CHUNK_SIZE = 1 << 20  # 1 MiB

ALGO_BY_LENGTH = {
    32: "md5", 40: "sha1", 56: "sha224", 64: "sha256", 96: "sha384", 128: "sha512",
}
_HEX_CHARS = set("0123456789abcdefABCDEF")
_ESCAPE_RE = re.compile(r"\\(.)")
_ESCAPE_MAP = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\"}


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


def read_manifest_text(path: str) -> str:
    """读取清单文本: 先按 utf-8, 失败退回 gbk, 再失败用替换字符兜底。"""
    with open(path, "rb") as fh:
        data = fh.read()
    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def parse_line(raw: str, lineno: int, forced_algo: str | None):
    """解析一行清单。

    返回 ("skip", None, None) / ("entry", (algo, digest, name), None) /
    ("error", None, 错误消息)。
    """
    line = raw.rstrip("\r\n")
    if not line.strip() or line.lstrip().startswith("#"):
        return "skip", None, None
    escaped = line.startswith("\\")
    if escaped:
        line = line[1:]
    i = 0
    while i < len(line) and line[i] in _HEX_CHARS:
        i += 1
    digest, rest = line[:i], line[i:]
    if not digest or not rest[:1].isspace():
        return "error", None, f"第 {lineno} 行无法解析: {line!r}"
    rest = rest[1:]                      # 吃掉哈希后的第一个空白
    if rest[:1] in (" ", "*"):           # GNU 的文本/二进制模式标记
        rest = rest[1:]
    name = rest.strip()
    if not name:
        return "error", None, f"第 {lineno} 行缺少文件名: {line!r}"
    if escaped:
        name = _ESCAPE_RE.sub(lambda m: _ESCAPE_MAP.get(m.group(1), m.group(1)), name)
    algo = forced_algo or ALGO_BY_LENGTH.get(len(digest))
    if algo is None:
        return "error", None, f"第 {lineno} 行哈希长度 {len(digest)} 无法识别算法 (可用 -a 指定)"
    return "entry", (algo, digest, name), None


def main(argv: list[str] | None = None) -> int:
    _setup_stdio()
    parser = argparse.ArgumentParser(
        prog="hash-verify",
        description="核对 sha256sum/md5sum 格式清单与本地文件是否一致。",
    )
    parser.add_argument("manifest", metavar="MANIFEST", help="校验和清单文件")
    parser.add_argument("-a", "--algorithm", metavar="ALGO", default=None,
                        help="强制所有条目使用该算法 (默认按哈希长度自动识别)")
    parser.add_argument("--base", metavar="DIR", default=None,
                        help="相对路径的基准目录 (默认: 清单文件所在目录)")
    parser.add_argument("-q", "--quiet", action="store_true", help="只输出失败项与汇总")
    args = parser.parse_args(argv)

    forced = None
    if args.algorithm:
        forced = args.algorithm.lower()
        try:
            hashlib.new(forced)
        except (ValueError, TypeError):
            print(f"hash-verify: 不支持的算法: {args.algorithm}", file=sys.stderr)
            return 2

    try:
        text = read_manifest_text(args.manifest)
    except OSError as exc:
        print(f"hash-verify: 无法读取清单 {args.manifest}: {exc.strerror or exc}",
              file=sys.stderr)
        return 2

    base = args.base or os.path.dirname(os.path.abspath(args.manifest))

    ok = mismatch = open_errors = parse_errors = 0
    for lineno, raw in enumerate(text.split("\n"), 1):
        status, payload, message = parse_line(raw, lineno, forced)
        if status == "skip":
            continue
        if status == "error":
            parse_errors += 1
            print(f"hash-verify: {message}", file=sys.stderr)
            continue
        algo, digest, name = payload
        path = name if os.path.isabs(name) else os.path.join(base, name)
        try:
            actual = hash_file(path, algo)
        except OSError as exc:
            open_errors += 1
            print(f"{path}: FAILED open or read ({exc.strerror or exc})")
            continue
        if actual.lower() == digest.lower():
            ok += 1
            if not args.quiet:
                print(f"{path}: OK")
        else:
            mismatch += 1
            print(f"{path}: FAILED")

    checked = ok + mismatch + open_errors
    print(f"汇总: 核对 {checked} 个文件: 通过 {ok}, 不匹配 {mismatch}, "
          f"读取失败 {open_errors}; 清单解析错误 {parse_errors} 行")
    if parse_errors or open_errors:
        return 2
    if checked == 0:
        print("hash-verify: 清单中没有任何有效校验和条目", file=sys.stderr)
        return 1
    return 1 if mismatch else 0


if __name__ == "__main__":
    sys.exit(main())
