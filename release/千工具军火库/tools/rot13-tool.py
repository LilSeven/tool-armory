#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ROT13 / ROT47 可逆文本变换工具。

ROT13: 只旋转 26 个英文字母(A-Z/a-z)13 位，其余字符不变；
ROT47: 只旋转 ASCII 33..126 共 94 个可打印字符 47 位，其余字符不变。
两者都是自反变换(再执行一次即还原原文)，因此不区分加密与解密。

用法:
    python rot13-tool.py [-m {rot13,rot47}] [文本]
    echo '文本' | python rot13-tool.py [-m rot47]
    python rot13-tool.py -s -m rot47       # -s: stdin 输入去掉末尾一个换行

示例:
    $ python rot13-tool.py 'Hello, World!'
    Uryyb, Jbeyq!
    $ python rot13-tool.py -m rot47 'Hello, World!'
    w6==@[ (@C=5P
    $ printf 'Uryyb, Jbeyq!' | python rot13-tool.py
    Hello, World!
"""

from __future__ import annotations

import argparse
import codecs
import sys


def rot13(text: str) -> str:
    """ROT13：借助标准库内置的 rot_13 编解码器。"""
    return codecs.encode(text, "rot_13")


def rot47(text: str) -> str:
    """ROT47：对 ASCII 33..126 的可打印字符整体旋转 47 位。"""
    return "".join(
        chr(33 + (ord(ch) - 33 + 47) % 94) if 33 <= ord(ch) <= 126 else ch
        for ch in text
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="对文本做 ROT13(字母)或 ROT47(可打印 ASCII)变换；两者均为自反变换",
    )
    parser.add_argument("text", nargs="?", default=None,
                        help="待变换文本；省略时从 stdin 读取")
    parser.add_argument("-m", "--mode", choices=("rot13", "rot47"),
                        default="rot13", help="变换方式(默认 rot13)")
    parser.add_argument("-s", "--strip", action="store_true",
                        help="stdin 输入时去掉末尾一个换行")
    args = parser.parse_args(argv)

    text = args.text
    if text is None:
        if sys.stdin.isatty():
            parser.error("未提供文本：请用参数传入，或通过管道从 stdin 读取")
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        if args.strip and raw.endswith("\n"):
            raw = raw[:-1]
            if raw.endswith("\r"):
                raw = raw[:-1]
        text = raw

    print(rot13(text) if args.mode == "rot13" else rot47(text))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
