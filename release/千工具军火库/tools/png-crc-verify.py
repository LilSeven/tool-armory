#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG CRC 校验器：用 zlib.crc32 逐一校验 PNG 每个 chunk 的 CRC32，报告损坏块的位置。

检查内容：
  * 8 字节 PNG 签名；
  * 每个 chunk（含 IHDR / IDAT / tEXt / IEND ...）的 CRC32：对“块类型 + 块数据”
    用 zlib.crc32 重算，并与块尾存储的 CRC 比对；
  * 结构问题：块截断、非法块类型、缺少 IEND、IEND 之后有多余数据。

用法：
    python png-crc-verify.py <image.png> [-q]

选项：
    -q, --quiet   不逐块列出，仅输出汇总

退出码：
    0 = 全部 chunk 的 CRC 与结构均正常
    1 = 发现 CRC 不匹配或结构问题
    2 = 文件不存在 / 无法读取 / 不是 PNG

示例：
    python png-crc-verify.py photo.png
    python png-crc-verify.py broken.png || echo "file damaged"
"""

import argparse
import struct
import sys
import zlib

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def is_valid_type(raw):
    """块类型必须是 4 个 ASCII 字母（A-Z / a-z）。"""
    return len(raw) == 4 and all(65 <= c <= 90 or 97 <= c <= 122 for c in raw)


def scan_chunks(data, problems, verbose=True):
    """扫描所有 chunk 并记录问题，返回 (chunk 总数, CRC 正常数)。"""
    pos = 8
    index = 0
    total = ok = 0
    seen_iend = False
    struct_broken = False
    while pos < len(data):
        if len(data) - pos < 8:
            problems.append("offset %d：剩余 %d 字节不足一个块头（文件截断）"
                            % (pos, len(data) - pos))
            struct_broken = True
            break
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        raw_type = data[pos + 4:pos + 8]
        if not is_valid_type(raw_type):
            problems.append("offset %d：块类型字节非法（hex %s）"
                            % (pos + 4, raw_type.hex()))
            struct_broken = True
            break
        name = raw_type.decode("latin-1")
        chunk_end = pos + 8 + length + 4
        if chunk_end > len(data):
            problems.append("offset %d：块 %s 声明数据长 %d，文件仅剩 %d 字节（块截断）"
                            % (pos, name, length, len(data) - pos - 8))
            struct_broken = True
            break
        cdata = data[pos + 8:pos + 8 + length]
        stored = struct.unpack(">I", data[pos + 8 + length:chunk_end])[0]
        calc = zlib.crc32(raw_type + cdata) & 0xFFFFFFFF
        total += 1
        if stored == calc:
            ok += 1
            line = "CRC OK"
        else:
            line = "CRC FAIL (stored=%08x, calc=%08x)" % (stored, calc)
            problems.append("chunk #%d %s（offset %d，数据 %d 字节）CRC 不匹配："
                            "存储 %08x，重算 %08x"
                            % (index, name, pos, length, stored, calc))
        if verbose:
            print("  #%-3d %-5s offset=%-9d len=%-9d %s"
                  % (index, name, pos, length, line))
        if raw_type == b"IEND":
            seen_iend = True
            if chunk_end < len(data):
                problems.append("IEND 之后仍有 %d 字节数据（offset %d 起）"
                                % (len(data) - chunk_end, chunk_end))
            break
        pos = chunk_end
        index += 1
    if not seen_iend and not struct_broken:
        problems.append("扫描结束仍未找到 IEND 块（PNG 数据流不完整）")
    return total, ok


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(
        description="校验 PNG 各 chunk 的 CRC32，报告损坏块位置")
    ap.add_argument("file", help="PNG 文件路径")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="不逐块列出，仅输出汇总")
    args = ap.parse_args(argv)

    try:
        with open(args.file, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        print("错误：无法读取文件：%s" % exc, file=sys.stderr)
        return 2
    if len(data) < 8 or data[:8] != PNG_SIG:
        print("错误：不是 PNG 文件（8 字节签名不符）", file=sys.stderr)
        return 2

    print("PNG CRC 校验：%s（%d 字节）" % (args.file, len(data)))
    problems = []
    total, ok = scan_chunks(data, problems, verbose=not args.quiet)
    print("汇总：%d 个 chunk，CRC 正常 %d 个，问题 %d 个"
          % (total, ok, len(problems)))
    for item in problems:
        print("  ! " + item)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
