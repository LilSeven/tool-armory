#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""随机密钥文件（keyfile）生成器。

用途:
    用系统安全随机源（secrets/os.urandom）生成指定字节数的 keyfile，
    可用作加密盘（如 LUKS、VeraCrypt、BitLocker 启动密钥）的外部密钥
    文件；同时输出 hexdump 预览与 SHA256 校验摘要，便于留档核对。

示例:
    python keyfile-gen.py -n 64 -o vault.key              # 生成 64 字节 keyfile
    python keyfile-gen.py -n 256 -o vault.key --hexdump-all   # 完整 hexdump
    python keyfile-gen.py -n 32 -o - > raw.bin            # 原始字节写到 stdout
    python keyfile-gen.py -n 64                           # 不落盘，仅预览与摘要

退出码: 0 成功；2 参数错误或输出文件已存在（可用 --force 覆盖）。
"""

import argparse
import hashlib
import os
import secrets
import sys

MIN_SIZE = 16
MAX_SIZE = 1 << 20      # 1 MiB
PREVIEW_BYTES = 64
HEX_WIDTH = 16


def _utf8_stdio():
    """让中文输出在管道/重定向时保持 UTF-8，避免 Windows 本地编码报错。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def hexdump(data, limit=None):
    """标准 hexdump：偏移 + 十六进制 + ASCII；limit 为预览字节数。"""
    shown = data if limit is None else data[:limit]
    lines = []
    for off in range(0, len(shown), HEX_WIDTH):
        chunk = shown[off:off + HEX_WIDTH]
        hexpart = " ".join("%02x" % b for b in chunk)
        hexpart = hexpart.ljust(HEX_WIDTH * 3 - 1)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append("%08x  %s  |%s|" % (off, hexpart, asc))
    if limit is not None and len(data) > limit:
        lines.append("...（共 %d 字节，此处仅预览前 %d 字节）" % (len(data), limit))
    return "\n".join(lines)


def main(argv=None):
    _utf8_stdio()
    ap = argparse.ArgumentParser(description="生成加密盘用随机 keyfile（纯标准库）")
    ap.add_argument("-n", "--size", type=int, default=64, metavar="N",
                    help="密钥字节数（%d..%d，默认 64）" % (MIN_SIZE, MAX_SIZE))
    ap.add_argument("-o", "--output", metavar="FILE",
                    help="输出文件路径；'-' 表示把原始字节写到 stdout")
    ap.add_argument("--hexdump-all", action="store_true",
                    help="hexdump 显示全部字节（默认只预览前 %d 字节）" % PREVIEW_BYTES)
    ap.add_argument("--force", action="store_true", help="允许覆盖已存在的输出文件")
    args = ap.parse_args(argv)

    n = args.size
    if not (MIN_SIZE <= n <= MAX_SIZE):
        print("错误: -n 必须在 %d..%d 之间，收到 %d" % (MIN_SIZE, MAX_SIZE, n),
              file=sys.stderr)
        return 2

    key = secrets.token_bytes(n)
    digest = hashlib.sha256(key).hexdigest()

    if args.output == "-":
        sys.stdout.buffer.write(key)
        sys.stdout.buffer.flush()
        return 0

    if args.output:
        if os.path.exists(args.output) and not args.force:
            print("错误: 输出文件已存在: %s（加 --force 可覆盖）" % args.output,
                  file=sys.stderr)
            return 2
        try:
            with open(args.output, "wb" if args.force else "xb") as f:
                f.write(key)
        except OSError as e:
            print("错误: 无法写入 %s: %s" % (args.output, e), file=sys.stderr)
            return 2
        print("已生成 keyfile: %s" % args.output)
    else:
        print("未指定 -o，以下仅预览（不写入磁盘）")

    print("大小  : %d 字节" % n)
    print("SHA256: %s" % digest)
    print()
    print(hexdump(key, None if args.hexdump_all else PREVIEW_BYTES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
