#!/usr/bin/env python3
"""hex-dump.py — 类 xxd 的十六进制查看器(单文件, 仅标准库)。

用途:
    以 "8 位十六进制偏移 + 冒号 + 十六进制列(默认 16 字节/行、按 2 字节分组) +
    两个空格 + 可打印 ASCII 栏(不可打印字节显示 '.')" 的 xxd 风格查看文件或 stdin。
    支持跳过开头字节(--skip, 支持 0x 十六进制)、限制显示字节数(--length)与
    行数(--lines), 适合快速检查二进制文件头、协议报文、日志中的不可见字符。

示例:
    python hex-dump.py file.bin
    python hex-dump.py file.bin --cols 8 --group 1
    python hex-dump.py file.bin --skip 0x100 --length 64
    python hex-dump.py file.bin --lines 20
    python hex-dump.py - < file.bin
"""

from __future__ import annotations

import argparse
import sys


def parse_int(text):
    """十进制或 0x/0o/0b 前缀整数。"""
    t = text.strip().lower()
    try:
        if t.startswith(("0x", "0o", "0b")):
            return int(t, 0)
        return int(t, 10)
    except ValueError:
        raise argparse.ArgumentTypeError("invalid integer: %r" % text)


def dump(fin, fout, cols, group, max_lines=None, max_bytes=None, start=0):
    """核心转储: 逐行读取并写出, 返回处理的字节数。输出为 ASCII 字节流。"""
    groups = (cols + group - 1) // group
    hex_width = groups * (2 * group) + (groups - 1)   # 十六进制区总宽(含组间空格)
    off = start
    lines = 0
    while ((max_lines is None or lines < max_lines)
           and (max_bytes is None or off - start < max_bytes)):
        want = cols
        if max_bytes is not None:
            want = min(want, max_bytes - (off - start))
        data = fin.read(want)
        if not data:
            break
        hex_area = " ".join(data[i:i + group].hex() for i in range(0, len(data), group))
        ascii_area = "".join(chr(b) if 0x20 <= b <= 0x7E else "." for b in data)
        fout.write(("%08x: %-*s  %s\n" % (off, hex_width, hex_area, ascii_area))
                   .encode("ascii"))
        off += len(data)
        lines += 1
    return off - start


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="hex-dump",
        description="类 xxd 的十六进制查看器: 偏移 + 十六进制列 + ASCII 栏。")
    parser.add_argument("file", nargs="?", default="-",
                        help="目标文件; '-' 或省略表示 stdin")
    parser.add_argument("--cols", type=int, default=16, help="每行字节数(默认 16)")
    parser.add_argument("--group", type=int, default=2,
                        help="十六进制分组的字节数(默认 2, xxd 风格)")
    parser.add_argument("--lines", type=parse_int, default=None,
                        help="最多显示的行数")
    parser.add_argument("--skip", type=parse_int, default=0,
                        help="跳过文件开头的字节数(支持 0x 写法)")
    parser.add_argument("--length", type=parse_int, default=None,
                        help="最多显示的字节数")
    args = parser.parse_args(argv)

    if args.cols < 1:
        parser.error("--cols must be >= 1")
    if args.group < 1:
        parser.error("--group must be >= 1")
    if args.lines is not None and args.lines < 0:
        parser.error("--lines must be >= 0")
    if args.skip < 0:
        parser.error("--skip must be >= 0")
    if args.length is not None and args.length < 0:
        parser.error("--length must be >= 0")

    try:
        if args.file == "-":
            fin = sys.stdin.buffer
            in_close = False
        else:
            fin = open(args.file, "rb")
            in_close = True
    except OSError as exc:
        print("hex-dump: cannot open file: %s" % exc, file=sys.stderr)
        return 1

    try:
        try:
            if args.skip:
                if fin.seekable():
                    fin.seek(args.skip)
                else:  # stdin 等不可回溯流: 逐块丢弃
                    remaining = args.skip
                    while remaining > 0:
                        dropped = fin.read(min(65536, remaining))
                        if not dropped:
                            break
                        remaining -= len(dropped)
            dump(fin, sys.stdout.buffer, args.cols, args.group,
                 args.lines, args.length, start=args.skip)
        finally:
            sys.stdout.buffer.flush()
    except OSError as exc:
        print("hex-dump: read failed: %s" % exc, file=sys.stderr)
        return 1
    finally:
        if in_close:
            fin.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
