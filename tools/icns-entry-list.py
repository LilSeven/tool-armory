#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ICNS 条目列表器(icns-entry-list) —— 解析 ICNS 图标包目录，列出每种内嵌图标类型代码与像素尺寸。

用途:
    读取 macOS .icns 文件：校验 'icns' 魔数与大端总长字段，然后顺序遍历每个
    子块(OSType 类型代码 + 大端长度)，输出每种的类型代码、文件偏移、块长、
    对应像素尺寸(如 128x128、32x32 即 16x16@2x)以及载荷格式嗅探
    (PNG / JP2 / JPEG / TIFF / raw)。

用法:
    python icns-entry-list.py <file.icns> [--json]
    python icns-entry-list.py --make-sample <out.icns>   生成含 4 个图标的示例
    python icns-entry-list.py --selftest                 构造示例输入并自校验

示例:
    python icns-entry-list.py app.icns
    python icns-entry-list.py app.icns --json
    python icns-entry-list.py --make-sample demo.icns
    python icns-entry-list.py --selftest

退出码: 0=成功; 1=不是 ICNS 或目录损坏; 2=命令行用法错误。
仅使用 Python 标准库(argparse/json/struct/zlib/tempfile/os)。
"""

import argparse
import json
import os
import struct
import sys
import tempfile
import zlib

MAGIC = b"icns"

# 类型代码 -> (像素边长, 说明)；None 表示未知尺寸
ICNS_TYPES = {
    "ICON": (32, "32x32 classic 1-bit"),
    "ICN#": (32, "32x32 1-bit + mask"),
    "icm#": (16, "16x16 1-bit + mask"),
    "icm4": (16, "16x16 4bpp"),
    "icm8": (16, "16x16 8bpp"),
    "ics#": (16, "16x16 1-bit + mask"),
    "ics4": (16, "16x16 4bpp"),
    "ics8": (16, "16x16 8bpp"),
    "is32": (16, "16x16 32bpp ARGB (PackBits)"),
    "s8mk": (16, "16x16 8-bit mask"),
    "icl4": (32, "32x32 4bpp"),
    "icl8": (32, "32x32 8bpp"),
    "il32": (32, "32x32 32bpp ARGB (PackBits)"),
    "l8mk": (32, "32x32 8-bit mask"),
    "ich#": (48, "48x48 1-bit + mask"),
    "ich4": (48, "48x48 4bpp"),
    "ich8": (48, "48x48 8bpp"),
    "ih32": (48, "48x48 32bpp ARGB (PackBits)"),
    "h8mk": (48, "48x48 8-bit mask"),
    "it32": (128, "128x128 32bpp ARGB (PackBits)"),
    "t8mk": (128, "128x128 8-bit mask"),
    "ic04": (16, "16x16 ARGB"),
    "ic05": (32, "32x32 ARGB"),
    "ic07": (128, "128x128 PNG/JPEG2000"),
    "ic08": (256, "256x256 PNG/JPEG2000"),
    "ic09": (512, "512x512 PNG/JPEG2000"),
    "ic10": (1024, "512x512@2x PNG/JPEG2000"),
    "ic11": (32, "16x16@2x PNG/JPEG2000"),
    "ic12": (64, "32x32@2x PNG/JPEG2000"),
    "ic13": (256, "128x128@2x PNG/JPEG2000"),
    "ic14": (512, "256x256@2x PNG/JPEG2000"),
    "ic15": (1024, "512x512@2x PNG/JPEG2000"),
    "icp4": (16, "16x16 PNG"),
    "icp5": (32, "32x32 PNG"),
    "icp6": (64, "64x64 PNG"),
    "icp7": (128, "128x128 PNG"),
    "TOC ": (0, "table of contents (icns v2)"),
}


class ICNSError(ValueError):
    """ICNS 解析失败。"""


def sniff_payload(payload):
    if payload[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if payload[:4] == b"\x00\x00\x00\x0c" and payload[4:8] == b"jP  ":
        return "JP2"
    if payload[:2] == b"\xff\xd8":
        return "JPEG"
    if payload[:4] in (b"II*\x00", b"MM\x00*"):
        return "TIFF"
    return "raw"


def parse_icns(data):
    if data[:4] != MAGIC:
        raise ICNSError("not an ICNS file (magic=%r)" % bytes(data[:4]))
    if len(data) < 8:
        raise ICNSError("too short for the 8-byte ICNS header")
    declared = struct.unpack_from(">I", data, 4)[0]
    warnings = []
    if declared > len(data):
        warnings.append("declared length %d exceeds file size %d" % (declared, len(data)))
        end = len(data)
    else:
        end = declared
        if declared < len(data):
            warnings.append("%d trailing byte(s) after declared end %d"
                            % (len(data) - declared, declared))

    entries = []
    pos = 8
    while pos < end:
        if pos + 8 > end:
            raise ICNSError("truncated chunk header at offset %d" % pos)
        raw_type = data[pos:pos + 4]
        length = struct.unpack_from(">I", data, pos + 4)[0]
        if length < 8:
            raise ICNSError("chunk %r at offset %d: length %d < 8"
                            % (bytes(raw_type), pos, length))
        if pos + length > end:
            raise ICNSError("chunk %r at offset %d overruns the declared end (len=%d)"
                            % (bytes(raw_type), pos, length))
        payload = data[pos + 8:pos + length]
        code = raw_type.decode("latin-1")
        pixels, label = ICNS_TYPES.get(code, (None, "unknown type"))
        entries.append({
            "type": code,
            "offset": pos,
            "length": length,
            "payload_length": length - 8,
            "pixels": pixels,
            "pixel_size": ("%dx%d" % (pixels, pixels)) if pixels else "?",
            "label": label,
            "payload_format": sniff_payload(payload),
        })
        pos += length
    return {
        "file_size": len(data),
        "declared_size": declared,
        "entries": entries,
        "warnings": warnings,
    }


def format_text(info):
    lines = [
        "file: %s" % info.get("path", "<memory>"),
        "size: %d bytes (header declares %d)" % (info["file_size"], info["declared_size"]),
        "type   offset  length  payload  pixels   format  note",
    ]
    for e in info["entries"]:
        lines.append("%-6s %6d %7d %8d %-8s %-7s %s" % (
            e["type"], e["offset"], e["length"], e["payload_length"],
            e["pixel_size"], e["payload_format"], e["label"]))
    lines.append("%d entr%s" % (len(info["entries"]),
                                "y" if len(info["entries"]) == 1 else "ies"))
    for w in info["warnings"]:
        lines.append("warning: %s" % w)
    return "\n".join(lines)


def make_png(width, height):
    """构造一张真实的 8-bit RGB PNG(逐行渐变)，用作 icns 载荷。"""
    def chunk(ctype, payload):
        return (struct.pack(">I", len(payload)) + ctype + payload +
                struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = bytearray()
    for y in range(height):
        v = (y * 5) % 256
        rows += b"\x00" + bytes((v, v, v)) * width
    idat = zlib.compress(bytes(rows), 9)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def make_sample():
    """示例 icns：ic07/ic08 两个 PNG 图标 + is32 像素数据 + s8mk 掩码。"""
    def entry(code, payload):
        return struct.pack(">4sI", code.encode("ascii"), 8 + len(payload)) + payload

    body = (entry("ic07", make_png(128, 128)) +
            entry("ic08", make_png(256, 256)) +
            entry("is32", b"\x00" * 64) +
            entry("s8mk", b"\x00" * 32))
    return b"icns" + struct.pack(">I", 8 + len(body)) + body


def selftest():
    # 1) 正常目录解析
    info = parse_icns(make_sample())
    types = [e["type"] for e in info["entries"]]
    assert types == ["ic07", "ic08", "is32", "s8mk"], types
    sizes = [e["pixel_size"] for e in info["entries"]]
    assert sizes == ["128x128", "256x256", "16x16", "16x16"], sizes
    formats = [e["payload_format"] for e in info["entries"]]
    assert formats == ["PNG", "PNG", "raw", "raw"], formats
    assert info["declared_size"] == info["file_size"] and not info["warnings"]
    print("  [ok] 4 entries listed with sizes and payload sniffing")

    # 2) @2x 类型映射
    assert ICNS_TYPES["ic11"][0] == 32 and "@2x" in ICNS_TYPES["ic11"][1]
    assert ICNS_TYPES["ic10"][0] == 1024 and "@2x" in ICNS_TYPES["ic10"][1]
    print("  [ok] @2x scale types mapped (ic10=1024, ic11=32)")

    # 3) 坏魔数 / 非法块长必须报错
    for bad in (b"PNGS" + b"\x00" * 40,
                b"icns\x00\x00\x00\x14\x00\x00\x00\x03junkjunk"):
        try:
            parse_icns(bad)
        except ICNSError:
            pass
        else:
            raise AssertionError("bad input accepted: %r" % bad[:8])
    print("  [ok] bad magic / bad chunk length rejected")

    # 4) 临时文件链路 + 文本/JSON 输出
    with tempfile.NamedTemporaryFile(suffix=".icns", delete=False) as fh:
        fh.write(make_sample())
        path = fh.name
    try:
        with open(path, "rb") as fh:
            info = parse_icns(fh.read())
        text = format_text(dict(info, path=path))
        assert "ic07" in text and "128x128" in text
        assert json.loads(json.dumps(info))["declared_size"] > 0
    finally:
        os.unlink(path)
    print("  [ok] temp-file round-trip, text+json output")

    print("selftest PASS (4 checks)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="icns-entry-list",
        description="解析 ICNS 图标包目录, 列出每种内嵌图标类型代码与像素尺寸")
    parser.add_argument("file", nargs="?", help=".icns 文件路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--make-sample", metavar="OUT",
                        help="生成示例 icns(含 PNG 载荷)到 OUT 后退出")
    parser.add_argument("--selftest", action="store_true",
                        help="运行内置自测后退出")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.make_sample:
        blob = make_sample()
        with open(args.make_sample, "wb") as fh:
            fh.write(blob)
        print("wrote %d-byte sample ICNS to %s" % (len(blob), args.make_sample))
        return 0
    if not args.file:
        parser.error("need an .icns file (or --selftest / --make-sample)")
    try:
        with open(args.file, "rb") as fh:
            info = parse_icns(fh.read())
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    except ICNSError as exc:
        print("error: %s: %s" % (args.file, exc), file=sys.stderr)
        return 1
    info["path"] = args.file
    print(json.dumps(info, indent=2) if args.json else format_text(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
