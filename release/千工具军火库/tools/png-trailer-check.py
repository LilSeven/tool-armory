#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG 尾部检查 —— 检查 IEND 之后是否残留附加数据。

顺序解析 PNG 块流，定位 IEND 块结束偏移；若文件在该偏移之后仍有字节，
则报告残留字节数、起始偏移与前 32 字节的十六进制预览，并提示残留数据
是否以 PNG 签名开头（常见于把另一个 PNG/文件追加到图片尾部做隐写）。
顺带报告块 CRC 校验失败、IEND 数据长度非 0、块流截断或缺少 IEND 等异常。

用法:
    python png-trailer-check.py <文件.png>

退出码:
    0 = 无残留数据（IEND 即文件末尾）
    1 = 发现残留数据，或块流截断 / 缺少 IEND 等结构异常
    2 = 文件不存在、无法读取，或 PNG 签名不符

示例:
    python png-trailer-check.py shot.png
    python png-trailer-check.py "K:/pics/suspect.png"

仅使用 Python 标准库, 需 Python 3.7+。
"""

import argparse
import struct
import sys
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def setup_stdio():
    """Windows 控制台/管道下强制 UTF-8 输出, 避免中文乱码或崩溃。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_chunks(blob):
    """解析 PNG 块流, 在 IEND 块之后或结构异常处停止。

    返回 (chunks, stop_offset, problem):
      chunks      -> [(offset, type_bytes, payload, crc_ok)]
                     offset 为块长度字段的起始偏移, crc_ok 为 CRC 是否匹配;
      stop_offset -> 解析停止位置(干净文件应等于 len(blob));
      problem     -> None 或结构异常描述字符串。
    """
    chunks = []
    problem = None
    pos = 8
    n = len(blob)
    stopped_at_iend = False
    while pos + 8 <= n:
        (length,) = struct.unpack(">I", blob[pos:pos + 4])
        ctype = blob[pos + 4:pos + 8]
        end = pos + 12 + length
        if end > n:
            problem = ("偏移 %d 的 %s 块声明 %d 字节数据, 超出文件末尾(缺 %d 字节)"
                       % (pos, ctype.decode("latin-1"), length, end - n))
            break
        payload = blob[pos + 8:pos + 8 + length]
        (crc_stored,) = struct.unpack(">I", blob[end - 4:end])
        crc_ok = (zlib.crc32(ctype + payload) & 0xFFFFFFFF) == crc_stored
        chunks.append((pos, ctype, payload, crc_ok))
        pos = end
        if ctype == b"IEND":
            stopped_at_iend = True
            break
    if problem is None and not stopped_at_iend and pos < n:
        problem = "偏移 %d 起剩余 %d 字节, 不足以构成完整块" % (pos, n - pos)
    return chunks, pos, problem


def hex_preview(buf, limit=32):
    head = buf[:limit]
    hx = " ".join("%02X" % c for c in head)
    text = "".join(chr(c) if 32 <= c < 127 else "." for c in head)
    suffix = " ..." if len(buf) > limit else ""
    return "%s%s |%s|" % (hx, suffix, text)


def main(argv=None):
    setup_stdio()
    ap = argparse.ArgumentParser(
        description="检查 PNG 的 IEND 之后是否残留附加数据, 报告字节数与偏移")
    ap.add_argument("file", help="PNG 文件路径")
    args = ap.parse_args(argv)

    try:
        with open(args.file, "rb") as fh:
            blob = fh.read()
    except OSError as exc:
        print("错误: 无法读取文件: %s" % exc, file=sys.stderr)
        return 2

    size = len(blob)
    print("文件: %s (%d 字节)" % (args.file, size))
    if not blob.startswith(SIGNATURE):
        print("错误: PNG 签名不符, 不是有效的 PNG 文件", file=sys.stderr)
        return 2
    print("PNG 签名: 正确")

    chunks, stop, problem = parse_chunks(blob)
    names = [c[1].decode("latin-1") for c in chunks]
    print("块流: %s" % (" -> ".join(names) if names else "(未解析出任何块)"))
    for off, ctype, _payload, crc_ok in chunks:
        if not crc_ok:
            print("警告: 偏移 %d 的 %s 块 CRC 校验失败"
                  % (off, ctype.decode("latin-1")))

    iends = [c for c in chunks if c[1] == b"IEND"]
    if not iends:
        print("未找到 IEND 块(解析停止于偏移 %d, 其后还有 %d 字节)"
              % (stop, size - stop))
        if problem:
            print("结构问题: %s" % problem)
        print("结果: 块流异常, 无法确认文件结尾 (退出码 1)")
        return 1

    off, _ctype, payload, _crc_ok = iends[-1]
    iend_end = off + 12 + len(payload)
    if payload:
        print("警告: IEND 块数据长度应为 0, 实际为 %d 字节" % len(payload))
    print("IEND 结束于偏移 %d, 文件总大小 %d" % (iend_end, size))

    trailing = size - iend_end
    if trailing == 0:
        print("结果: 无残留数据, IEND 即文件末尾 (退出码 0)")
        return 0

    trailer = blob[iend_end:]
    print("残留数据: %d 字节, 起始偏移 %d" % (trailing, iend_end))
    print("预览: %s" % hex_preview(trailer))
    if trailer.startswith(SIGNATURE):
        print("提示: 残留数据以 PNG 签名开头, 疑似追加了另一个 PNG 文件")
    if problem:
        print("提示: 残留数据无法解析为完整块流 (%s)" % problem)
    print("结果: 发现 IEND 之后残留 %d 字节 (退出码 1)" % trailing)
    return 1


if __name__ == "__main__":
    sys.exit(main())
