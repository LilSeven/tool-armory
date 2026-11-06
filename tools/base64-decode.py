#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""base64-decode.py —— 把 Base64 解码为文本/二进制。

用途：
    解码字面字符串、文件或 stdin 中的 Base64 数据。自动容忍并剔除换行符
    与空白（兼容 76 列等分行格式），并自动补齐缺失的 '=' padding。
    默认把解码后的原始字节写到 stdout（文本以原编码字节输出，Git Bash 的
    UTF-8 终端可直接阅读）；-o 可把结果写入二进制文件。

示例命令：
    echo "aGVsbG8=" | python base64-decode.py             # -> hello
    echo "aGVsbG8"  | python base64-decode.py             # 缺 padding 也能解码
    printf 'aGVs\\nbG8=\\n' | python base64-decode.py      # 带换行也能解码
    python base64-decode.py out.b64                       # 解码文件内容到 stdout
    python base64-decode.py photo.b64 -o photo.png        # 还原二进制文件
    python base64-decode.py -s "aGVsbG8="                 # 直接解码字符串

退出码：0 成功；1 读写失败或输入不是合法 Base64；2 命令行参数错误。
仅使用 Python 标准库（argparse / base64）。
"""

import argparse
import base64
import sys

_ALPHABET = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="base64-decode.py",
        description="解码 Base64 为文本/二进制，容忍换行符并自动补齐缺失的 padding。",
    )
    p.add_argument("input", nargs="?", default=None,
                   help="含 Base64 的文件路径；省略或为 '-' 时从 stdin 读取")
    p.add_argument("-s", "--string", default=None,
                   help="直接解码给定的 Base64 字符串（优先于文件/stdin）")
    p.add_argument("-o", "--output", default=None,
                   help="输出文件（写入解码后的原始字节）；省略则写到 stdout")
    return p


def load_compact_b64(args: argparse.Namespace) -> str:
    if args.string is not None:
        text = args.string
    elif args.input and args.input != "-":
        with open(args.input, "rb") as f:
            text = f.read().decode("utf-8", errors="replace")
    else:
        text = sys.stdin.buffer.read().decode("utf-8", errors="replace")

    compact = "".join(text.split())          # 剔除换行/空格/tab 等所有空白
    bad = sorted({c for c in compact if c not in _ALPHABET and c != "="})
    if bad:
        preview = " ".join(repr(c) for c in bad[:5])
        raise ValueError(f"输入含有非 Base64 字符: {preview}")
    compact = compact.rstrip("=")
    compact += "=" * (-len(compact) % 4)     # 自动补齐缺失的 padding
    return compact


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        compact = load_compact_b64(args)
        data = base64.b64decode(compact, validate=True)
    except (ValueError, OSError) as exc:
        print(f"base64-decode: {exc}", file=sys.stderr)
        return 1

    try:
        if args.output:
            with open(args.output, "wb") as f:
                f.write(data)
        else:
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
    except OSError as exc:
        print(f"base64-decode: 写出失败: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
