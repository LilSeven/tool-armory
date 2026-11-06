#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""base85-tool.py —— Ascii85（a85）与 RFC 1924 Base85（b85）编码解码。

用途：
    对文本（-s）、文件或 stdin 数据做两种 Base85 变体的编码与解码：
      a85  Ascii85（PostScript/PDF/btoa 风格，'z' 压缩 4 个零字节，
           --adobe 加 <~ ~> 括帧）；对应标准库 base64.a85encode/a85decode。
      b85  RFC 1924 字母表（git/ZMQ 风格，注意不是 Z85）；
           对应标准库 base64.b85encode/b85decode。
    解码自动容忍并剔除空白；a85 解码自动识别 <~ ~> Adobe 括帧；
    -o 可把解码结果写入二进制文件。

示例命令：
    python base85-tool.py a85 enc -s "Hello"           # -> 87cURDZ
    python base85-tool.py a85 dec -s "87cURDZ"         # -> Hello
    python base85-tool.py a85 enc -s "Hello" --adobe   # -> <~87cURDZ~>
    python base85-tool.py b85 enc -s "Hello"           # -> NM&qnZv
    python base85-tool.py b85 dec -s "NM&qnZv" -o out.bin  # 解码到文件
    echo -n "data" | python base85-tool.py a85 enc     # 从 stdin 读入

退出码：0 成功；1 读写失败或输入不是合法 Base85；2 参数错误（argparse）。
仅使用 Python 标准库（argparse / base64）。
"""

import argparse
import base64
import sys

_CODEC_MAP = {"a85": "a85", "ascii85": "a85",
              "b85": "b85", "base85": "b85", "rfc1924": "b85"}
_ACTION_MAP = {"enc": "enc", "encode": "enc", "dec": "dec", "decode": "dec"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="base85-tool.py",
        description="Ascii85（a85）与 RFC 1924 Base85（b85）两种变体的编码解码。",
    )
    p.add_argument("codec", help="变体：a85/ascii85 或 b85/base85（RFC 1924）")
    p.add_argument("action", help="动作：enc/encode 或 dec/decode")
    p.add_argument("input", nargs="?", default=None,
                   help="输入文件；省略或为 '-' 时从 stdin 读取")
    p.add_argument("-s", "--string", default=None,
                   help="直接处理给定的字符串（优先于文件/stdin）")
    p.add_argument("-o", "--output", default=None,
                   help="输出文件；省略则写到 stdout（解码写入原始字节）")
    p.add_argument("-e", "--encoding", default="utf-8",
                   help="-s 文本所用编码，默认 utf-8")
    p.add_argument("--adobe", action="store_true",
                   help="a85 专用：编码时加 <~ ~> 括帧；解码时要求输入必须带括帧")
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


def encode_payload(codec: str, data: bytes, adobe: bool) -> str:
    if codec == "a85":
        return base64.a85encode(data, adobe=adobe).decode("ascii")
    return base64.b85encode(data).decode("ascii")


def decode_payload(codec: str, text: str, adobe: bool) -> bytes:
    compact = "".join(text.split())      # 剔除换行/空格/tab 等所有空白
    if codec == "a85":
        framed = (len(compact) >= 4 and compact.startswith("<~")
                  and compact.endswith("~>"))
        if adobe and not framed:
            raise ValueError("Adobe 模式要求输入以 <~ 开头、以 ~> 结尾")
        try:
            return base64.a85decode(compact, adobe=framed or adobe)
        except ValueError as exc:
            raise ValueError(f"a85 解码失败: {exc}") from None
    try:
        return base64.b85decode(compact)
    except ValueError as exc:
        raise ValueError(f"b85 解码失败: {exc}") from None


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    codec = _CODEC_MAP.get(args.codec.lower())
    action = _ACTION_MAP.get(args.action.lower())
    if codec is None:
        print(f"base85-tool: 未知变体 {args.codec!r}，"
              f"可用: a85/ascii85、b85/base85/rfc1924", file=sys.stderr)
        return 1
    if action is None:
        print(f"base85-tool: 未知动作 {args.action!r}，"
              f"可用: enc/encode、dec/decode", file=sys.stderr)
        return 1
    if args.adobe and codec != "a85":
        print("base85-tool: --adobe 仅适用于 a85 变体", file=sys.stderr)
        return 1
    try:
        if action == "enc":
            text = encode_payload(codec, read_bytes(args), args.adobe)
            payload = (text + "\n").encode("ascii")
        else:
            payload = decode_payload(codec, read_text(args), args.adobe)
        if args.output:
            with open(args.output, "wb") as f:
                f.write(payload)
        else:
            sys.stdout.buffer.write(payload)
            sys.stdout.buffer.flush()
    except (ValueError, OSError) as exc:
        print(f"base85-tool: {exc}", file=sys.stderr)
        return 1
    except LookupError:
        print(f"base85-tool: 未知编码名 {args.encoding!r}", file=sys.stderr)
        return 1
    except UnicodeEncodeError as exc:
        print(f"base85-tool: 文本无法按 {args.encoding!r} 编码: {exc}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
