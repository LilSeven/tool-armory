#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""base32-tool.py —— Base32（RFC 4648）与 Base16(hex) 编码解码，支持小写输出。

用途：
    对文本（-s）、文件或 stdin 数据做 Base32 / Base16(hex) 的编码与解码；
    -l 让编码输出使用小写（Base32 与 hex 均适用）；解码自动接受小写输入
    并容忍换行/空白；-o 可把结果写入文件（解码时写入原始字节）。

实现说明：
    Base16 直接使用标准库 binascii.hexlify / unhexlify；标准库 binascii
    未提供 Base32 例程（已用 dir(binascii) 核实），故按 RFC 4648 以位运算
    自行实现，输出与 base64.b32encode/b32decode 完全一致（用 0-11 字节
    样本交叉验证通过）。

示例命令：
    python base32-tool.py b32 enc -s "Hello"           # -> JBSWY3DP
    python base32-tool.py b32 dec -s "jbswy3dp"        # 小写输入亦可 -> Hello
    python base32-tool.py b16 enc -s "Hello"           # -> 48656C6C6F
    python base32-tool.py b16 enc -s "Hello" -l        # 小写 hex -> 48656c6c6f
    python base32-tool.py b16 dec -s "48656C6C6F"      # -> Hello
    python base32-tool.py b32 enc data.bin -o data.b32 # 编码文件到文件
    python base32-tool.py b32 dec data.b32 -o data.out # 解码文件到文件
    echo -n "hi" | python base32-tool.py b32 enc       # 从 stdin 读入

退出码：0 成功；1 读写失败、未知编码类型或输入非法；2 参数错误（argparse）。
仅使用 Python 标准库（argparse / binascii）。
"""

import argparse
import binascii
import sys

B32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
B32_REV = {c: i for i, c in enumerate(B32_ALPHABET)}

_CODEC_MAP = {"b32": "b32", "base32": "b32",
              "b16": "b16", "base16": "b16", "hex": "b16"}
_ACTION_MAP = {"enc": "enc", "encode": "enc", "dec": "dec", "decode": "dec"}


def b32_encode(data: bytes, lower: bool = False) -> str:
    """RFC 4648 Base32 编码（5 字节 -> 8 字符，'=' 补位）。"""
    acc = 0
    nbits = 0
    out = []
    for byte in data:
        acc = (acc << 8) | byte
        nbits += 8
        while nbits >= 5:
            nbits -= 5
            out.append(B32_ALPHABET[(acc >> nbits) & 0x1F])
            acc &= (1 << nbits) - 1
    if nbits:
        out.append(B32_ALPHABET[(acc << (5 - nbits)) & 0x1F])
    encoded = "".join(out) + "=" * ((-len(out)) % 8)
    return encoded.lower() if lower else encoded


def b32_decode(text: str) -> bytes:
    """RFC 4648 Base32 解码；容忍大小写与空白，末尾不足 8 位的剩余位忽略。"""
    compact = "".join(text.split()).rstrip("=").upper()
    if not compact:
        return b""
    bad = sorted({c for c in compact if c not in B32_REV})
    if bad:
        raise ValueError("非 Base32 字符: " + " ".join(bad[:5]))
    if len(compact) % 8 in (1, 3, 6):
        raise ValueError(f"Base32 长度非法（去 padding 后 {len(compact)} 字符）")
    acc = 0
    nbits = 0
    out = bytearray()
    for c in compact:
        acc = (acc << 5) | B32_REV[c]
        nbits += 5
        if nbits >= 8:
            nbits -= 8
            out.append((acc >> nbits) & 0xFF)
            acc &= (1 << nbits) - 1
    return bytes(out)


def b16_encode(data: bytes, lower: bool = False) -> str:
    encoded = binascii.hexlify(data).decode("ascii")
    return encoded.lower() if lower else encoded.upper()


def b16_decode(text: str) -> bytes:
    compact = "".join(text.split())
    try:
        return binascii.unhexlify(compact)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(f"非法 hex 输入: {exc}") from None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="base32-tool.py",
        description="Base32（RFC 4648）与 Base16(hex) 编解码，支持小写输出。",
    )
    p.add_argument("codec", help="编码类型：b32/base32 或 b16/base16/hex")
    p.add_argument("action", help="动作：enc/encode 或 dec/decode")
    p.add_argument("input", nargs="?", default=None,
                   help="输入文件；省略或为 '-' 时从 stdin 读取")
    p.add_argument("-s", "--string", default=None,
                   help="直接处理给定的字符串（优先于文件/stdin）")
    p.add_argument("-o", "--output", default=None,
                   help="输出文件；省略则写到 stdout（解码写入原始字节）")
    p.add_argument("-l", "--lower", action="store_true",
                   help="编码输出使用小写（b32 与 hex 均适用）")
    p.add_argument("-e", "--encoding", default="utf-8",
                   help="-s 文本所用编码，默认 utf-8")
    return p


def read_bytes(args: argparse.Namespace) -> bytes:
    if args.string is not None:
        return args.string.encode(args.encoding)
    if args.input and args.input != "-":
        with open(args.input, "rb") as f:
            return f.read()
    return sys.stdin.buffer.read()


def read_text(args: argparse.Namespace) -> str:
    if args.string is not None:
        return args.string
    if args.input and args.input != "-":
        with open(args.input, "rb") as f:
            return f.read().decode("utf-8", errors="replace")
    return sys.stdin.buffer.read().decode("utf-8", errors="replace")


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    codec = _CODEC_MAP.get(args.codec.lower())
    action = _ACTION_MAP.get(args.action.lower())
    if codec is None:
        print(f"base32-tool: 未知编码类型 {args.codec!r}，"
              f"可用: b32/base32、b16/base16/hex", file=sys.stderr)
        return 1
    if action is None:
        print(f"base32-tool: 未知动作 {args.action!r}，"
              f"可用: enc/encode、dec/decode", file=sys.stderr)
        return 1
    try:
        if action == "enc":
            data = read_bytes(args)
            text = (b32_encode(data, args.lower) if codec == "b32"
                    else b16_encode(data, args.lower))
            payload = (text + "\n").encode("ascii")
        else:
            text_in = read_text(args)
            payload = (b32_decode(text_in) if codec == "b32"
                       else b16_decode(text_in))
        if args.output:
            with open(args.output, "wb") as f:
                f.write(payload)
        else:
            sys.stdout.buffer.write(payload)
            sys.stdout.buffer.flush()
    except (ValueError, OSError) as exc:
        print(f"base32-tool: {exc}", file=sys.stderr)
        return 1
    except LookupError:
        print(f"base32-tool: 未知编码名 {args.encoding!r}", file=sys.stderr)
        return 1
    except UnicodeEncodeError as exc:
        print(f"base32-tool: 文本无法按 {args.encoding!r} 编码: {exc}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
