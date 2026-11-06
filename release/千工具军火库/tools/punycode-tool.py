#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Punycode 域名转码：中文/国际化域名(IDN)与 xn-- ASCII 形式互相转换。

基于标准库 codecs 的 'idna' 编解码器（其内部使用 punycode 算法），
按标签(以 . 分隔)逐段转码，非 IDN 标签原样保留。无第三方依赖。

用法:
    python punycode-tool.py encode <unicode域名>     # Unicode -> xn--...
    python punycode-tool.py decode <xn--域名>        # xn--... -> Unicode
    python punycode-tool.py auto <域名>              # 自动判断方向(默认)
    echo 中文.com | python punycode-tool.py encode   # 省略文本参数时从 stdin 读取

示例:
    $ python punycode-tool.py encode 你好.世界
    xn--6qq79v.xn--rhqv96g
    $ python punycode-tool.py decode xn--6qq79v.xn--rhqv96g
    你好.世界
    $ python punycode-tool.py www.例子.com
    www.xn--fsqu00a.com
"""

from __future__ import annotations

import argparse
import codecs
import sys

ACE_PREFIX = "xn--"


def _reconfigure_streams() -> None:
    """让 stdout/stderr 在 Windows 各类终端与管道下尽量以 UTF-8 输出。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def to_punycode(domain: str) -> str:
    """Unicode 域名 -> xn-- Punycode 域名(纯 ASCII)。"""
    return codecs.encode(domain, "idna").decode("ascii")


def from_punycode(domain: str) -> str:
    """xn-- Punycode 域名 -> Unicode 域名。"""
    try:
        raw = domain.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("decode 方向的输入应为纯 ASCII 的 xn-- 域名") from exc
    return codecs.decode(raw, "idna")


def guess_mode(domain: str) -> str:
    """任一标签带 xn-- 前缀则视为 decode，否则视为 encode。"""
    labels = domain.lower().split(".")
    return "decode" if any(lb.startswith(ACE_PREFIX) for lb in labels) else "encode"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="中文/国际化域名与 xn-- Punycode 形式互相转换（codecs 'idna'）",
    )
    parser.add_argument(
        "mode", nargs="?", default=None,
        help="encode/decode/auto；省略时自动识别（默认）",
    )
    parser.add_argument(
        "text", nargs="?", default=None,
        help="待转换域名；省略时从 stdin 读取",
    )
    args = parser.parse_args(argv)

    mode, text = args.mode, args.text
    if text is None:
        stdin_text = None
        if not sys.stdin.isatty():
            stdin_text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        if stdin_text and stdin_text.strip():
            text = stdin_text  # stdin 优先: `tool encode < domains.txt`
        elif mode is not None:
            mode, text = "auto", mode  # 只给了 1 个参数 -> 视为待转换域名
    if mode not in (None, "encode", "decode", "auto"):
        parser.error(f"mode 只能是 encode/decode/auto，收到: {mode!r}")
    if text is None:
        parser.error("未提供域名：请用参数传入，或通过管道从 stdin 读取")
    text = text.strip()
    if not text:
        parser.error("未提供域名（参数与 stdin 均为空）")

    if mode in (None, "auto"):
        mode = guess_mode(text)

    try:
        result = to_punycode(text) if mode == "encode" else from_punycode(text)
    except (UnicodeError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    print(result)
    return 0


if __name__ == "__main__":
    _reconfigure_streams()
    sys.exit(main())
