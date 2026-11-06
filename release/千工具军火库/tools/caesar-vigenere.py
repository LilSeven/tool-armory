#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""凯撒(Caesar)移位与维吉尼亚(Vigenere)密码加解密：仅英文字母表内变换。

规则: 只变换 A-Z/a-z，大小写保留；数字、标点、空白等非字母字符原样输出。
维吉尼亚密钥只取英文字母（大小写不敏感），且仅在遇到被加密字母时推进密钥指针。

用法:
    python caesar-vigenere.py caesar   <enc|dec> <shift> [文本]
    python caesar-vigenere.py vigenere <enc|dec> <key>   [文本]
    echo '文本' | python caesar-vigenere.py <cipher> <enc|dec> <shift|key>

示例:
    $ python caesar-vigenere.py caesar enc 3 'Hello, World!'
    Khoor, Zruog!
    $ python caesar-vigenere.py caesar dec 3 'Khoor, Zruog!'
    Hello, World!
    $ python caesar-vigenere.py vigenere enc LEMON ATTACKATDAWN
    LXFOPVEFRNHR
    $ python caesar-vigenere.py vigenere dec LEMON LXFOPVEFRNHR
    ATTACKATDAWN
"""

from __future__ import annotations

import argparse
import sys

UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LOWER = "abcdefghijklmnopqrstuvwxyz"


def caesar(text: str, shift: int) -> str:
    """凯撒移位：shift 为任意整数（内部取模 26），负数等同解密方向。"""
    shift %= 26
    out = []
    for ch in text:
        if "A" <= ch <= "Z":
            out.append(UPPER[(UPPER.index(ch) + shift) % 26])
        elif "a" <= ch <= "z":
            out.append(LOWER[(LOWER.index(ch) + shift) % 26])
        else:
            out.append(ch)
    return "".join(out)


def vigenere(text: str, key: str, decrypt: bool = False) -> str:
    """维吉尼亚加解密：enc 时字符加密钥位移，dec 时减。"""
    key_stream = [UPPER.index(c) for c in key.upper() if "A" <= c <= "Z"]
    if not key_stream:
        raise ValueError("维吉尼亚密钥必须至少包含一个英文字母")
    out = []
    ki = 0
    for ch in text:
        if "A" <= ch <= "Z" or "a" <= ch <= "z":
            k = key_stream[ki % len(key_stream)]
            ki += 1
            table = UPPER if "A" <= ch <= "Z" else LOWER
            shift = (-k if decrypt else k) % 26
            out.append(table[(table.index(ch) + shift) % 26])
        else:
            out.append(ch)
    return "".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="凯撒移位与维吉尼亚密码的加密解密（仅字母表内变换，大小写保留）",
    )
    parser.add_argument("cipher", choices=("caesar", "vigenere"),
                        help="caesar=凯撒移位; vigenere=维吉尼亚")
    parser.add_argument("op", choices=("enc", "dec"),
                        help="enc=加密; dec=解密")
    parser.add_argument("key",
                        help="caesar: 移位量整数(可负); vigenere: 字母密钥")
    parser.add_argument("text", nargs="?", default=None,
                        help="待处理文本；省略时从 stdin 读取")
    args = parser.parse_args(argv)

    text = args.text
    if text is None:
        if sys.stdin.isatty():
            parser.error("未提供文本：请用参数传入，或通过管道从 stdin 读取")
        text = sys.stdin.buffer.read().decode("utf-8", errors="replace")

    if args.cipher == "caesar":
        try:
            shift = int(args.key)
        except ValueError:
            print(f"错误: caesar 的移位量必须是整数，收到: {args.key!r}",
                  file=sys.stderr)
            return 1
        result = caesar(text, -shift if args.op == "dec" else shift)
    else:
        try:
            result = vigenere(text, args.key, decrypt=(args.op == "dec"))
        except ValueError as exc:
            print(f"错误: {exc}", file=sys.stderr)
            return 1

    print(result)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
