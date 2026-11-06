#!/usr/bin/env python3
"""base64-stream-encode.py — 大文件分块流式 Base64 编码器(单文件, 仅标准库)。

用途:
    以固定块大小(默认 3 MiB, 向下取整为 3 的倍数)流式读取输入文件, 逐块 Base64 编码
    后写出, 内存占用恒定(只与块大小相关), 绝不整文件读入。块长为 3 的倍数保证各块
    编码结果可直接拼接, 与一次性 b64encode(整个文件) 的结果逐字节一致。--wrap 控制
    输出列宽换行(默认 76, 与 GNU base64 兼容; 0 表示不换行)。

示例:
    python base64-stream-encode.py big.iso big.iso.b64
    python base64-stream-encode.py big.iso - --wrap 0          # 不换行, 输出到 stdout
    python base64-stream-encode.py big.iso out.b64 --chunk 1M --progress
    python base64-stream-encode.py - out.b64 < data.bin        # 从 stdin 读入
"""

from __future__ import annotations

import argparse
import base64
import sys

UNITS = {"k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}


def parse_size(text):
    """解析 '3M' / '512k' / '1G' / '3145728' 之类的块大小, 返回字节数。"""
    t = text.strip().lower()
    if t.endswith("ib"):
        t = t[:-2]
    if len(t) >= 2 and t[-1] == "b" and (t[-2].isdigit() or t[-2] in UNITS):
        t = t[:-1]
    try:
        if t and t[-1] in UNITS:
            value = int(t[:-1]) * UNITS[t[-1]]
        else:
            value = int(t)
    except ValueError:
        raise argparse.ArgumentTypeError("invalid size: %r" % text)
    if value <= 0:
        raise argparse.ArgumentTypeError("size must be positive: %r" % text)
    return value


def encode_stream(fin, fout, chunk, wrap, progress=False):
    """分块流式编码。chunk 必须是 3 的倍数(末块除外), 拼接结果与整读编码一致。

    任意时刻只持有一个输入块及其编码结果, 内存占用恒定。返回已编码的原始字节数。
    """
    col = 0      # 当前输出行列位置(仅 wrap>0 时有意义, 跨块保持连续)
    total = 0
    while True:
        data = fin.read(chunk)
        if not data:
            break
        enc = base64.b64encode(data)
        if wrap > 0:
            while enc:
                room = wrap - col
                piece, enc = enc[:room], enc[room:]
                fout.write(piece)
                col += len(piece)
                if col >= wrap:
                    fout.write(b"\n")
                    col = 0
        else:
            fout.write(enc)
        total += len(data)
        if progress:
            print("\r%14d bytes encoded" % total, end="", flush=True, file=sys.stderr)
    if progress:
        print(file=sys.stderr)
    if wrap > 0 and col:
        fout.write(b"\n")
    return total


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    parser = argparse.ArgumentParser(
        prog="base64-stream-encode",
        description="分块流式把大文件编码为 Base64, 内存占用恒定, 不整读。")
    parser.add_argument("infile", nargs="?", default="-",
                        help="输入文件; '-' 或省略表示 stdin")
    parser.add_argument("outfile", nargs="?", default="-",
                        help="输出文件; '-' 或省略表示 stdout")
    parser.add_argument("--wrap", type=int, default=76, metavar="N",
                        help="每 N 个字符换行(默认 76; 0 表示不换行)")
    parser.add_argument("--chunk", type=parse_size, default=3 * 1024 * 1024,
                        metavar="SIZE",
                        help="块大小, 如 3M / 1M / 512k(默认 3M, 向下取整为 3 的倍数)")
    parser.add_argument("--progress", action="store_true", help="向 stderr 打印进度")
    args = parser.parse_args(argv)

    chunk = args.chunk
    if chunk % 3:
        chunk -= chunk % 3
        print("note: chunk size rounded down to %d bytes (multiple of 3)" % chunk,
              file=sys.stderr)
    if args.wrap < 0:
        parser.error("--wrap must be >= 0")

    try:
        if args.infile == "-":
            fin = sys.stdin.buffer
            in_close = False
        else:
            fin = open(args.infile, "rb")
            in_close = True
        try:
            if args.outfile == "-":
                sys.stdout.flush()
                fout = sys.stdout.buffer
                out_close = False
            else:
                fout = open(args.outfile, "wb")
                out_close = True
            try:
                encode_stream(fin, fout, chunk, args.wrap, args.progress)
            finally:
                if out_close:
                    fout.close()
                else:
                    fout.flush()
        finally:
            if in_close:
                fin.close()
    except OSError as exc:
        print("base64-stream-encode: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
