#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""base64-encode.py —— 把文本或文件编码为 Base64（RFC 4648 标准字母表）。

用途：
    将 -s 给定的文本、指定文件或 stdin 的内容编码为 Base64，输出到 stdout
    或 -o 指定的文件；-w 指定输出列宽（每 N 个 Base64 字符换一行，0 为
    不换行，默认 0）。输入按字节读取，不经过文本换码，适合任意二进制。

示例命令：
    python base64-encode.py -s "hello"                     # -> aGVsbG8=
    echo -n "hello" | python base64-encode.py              # 从 stdin 读入
    python base64-encode.py photo.png                      # 编码二进制文件
    python base64-encode.py data.bin -w 76 -o out.b64      # 76 列换行写入文件
    python base64-encode.py -s "你好"                      # 文本默认按 utf-8 编码

退出码：0 成功；1 读写失败或编码名未知；2 命令行参数错误（argparse）。
仅使用 Python 标准库（argparse / base64）。
"""

import argparse
import base64
import sys


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="base64-encode.py",
        description="把文本或文件编码为 Base64，支持从 stdin 读入与指定输出列宽。",
    )
    p.add_argument("input", nargs="?", default=None,
                   help="输入文件路径；省略或为 '-' 时从 stdin 读取")
    p.add_argument("-s", "--string", default=None,
                   help="直接编码给定的文本字符串（优先于文件/stdin）")
    p.add_argument("-o", "--output", default=None,
                   help="输出文件路径；省略则写到 stdout")
    p.add_argument("-w", "--width", type=int, default=0,
                   help="输出列宽（每 N 个 Base64 字符换行），0 表示不换行（默认）")
    p.add_argument("-e", "--encoding", default="utf-8",
                   help="-s 文本所用编码，默认 utf-8")
    return p


def read_payload(args: argparse.Namespace) -> bytes:
    if args.string is not None:
        return args.string.encode(args.encoding)
    if args.input and args.input != "-":
        with open(args.input, "rb") as f:
            return f.read()
    return sys.stdin.buffer.read()


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        data = read_payload(args)
    except OSError as exc:
        print(f"base64-encode: 读取输入失败: {exc}", file=sys.stderr)
        return 1
    except LookupError:
        print(f"base64-encode: 未知编码名 {args.encoding!r}", file=sys.stderr)
        return 1
    except UnicodeEncodeError as exc:
        print(f"base64-encode: 文本无法按 {args.encoding!r} 编码: {exc}",
              file=sys.stderr)
        return 1

    encoded = base64.b64encode(data)
    if args.width and args.width > 0:
        w = args.width
        lines = [encoded[i:i + w] for i in range(0, len(encoded), w)]
        payload = b"\n".join(lines)
        if payload:
            payload += b"\n"
    else:
        payload = encoded + b"\n"

    try:
        if args.output:
            with open(args.output, "wb") as f:
                f.write(payload)
        else:
            sys.stdout.buffer.write(payload)
            sys.stdout.buffer.flush()
    except OSError as exc:
        print(f"base64-encode: 写出失败: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
