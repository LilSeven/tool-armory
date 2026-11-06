#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG 块遍历器(png-chunk-walker) —— 按顺序列出 PNG 全部 chunk 的类型、长度与文件偏移，标注关键/辅助/私有位。

用途:
    校验 PNG 签名后按文件顺序遍历所有 chunk，对每个块输出：文件偏移、
    数据长度、类型码，并按 PNG 规范解码类型码的位标志：
    关键(critical)/辅助(ancillary)、公开(public)/私有(private)、
    保留位(reserved bit，置 1 即非法)、安全拷贝(safe-to-copy)；
    同时用 zlib.crc32 校验每块 CRC。附 IEND 缺失/IEND 后尾随字节等警告。

用法:
    python png-chunk-walker.py <file.png> [--json]
    python png-chunk-walker.py --make-sample <out.png>   生成含 5 个块的示例 PNG
    python png-chunk-walker.py --selftest                构造示例输入并自校验

示例:
    python png-chunk-walker.py image.png
    python png-chunk-walker.py image.png --json
    python png-chunk-walker.py --make-sample demo.png
    python png-chunk-walker.py --selftest

退出码: 0=成功(CRC 不匹配也算成功，只告警); 1=签名错误/结构截断; 2=命令行用法错误。
仅使用 Python 标准库(argparse/json/struct/zlib/tempfile/os)。
"""

import argparse
import json
import os
import struct
import sys
import tempfile
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"

PNG_TYPES = {
    "IHDR": "image header", "PLTE": "palette", "IDAT": "image data",
    "IEND": "image end", "tRNS": "transparency", "gAMA": "image gamma",
    "cHRM": "chromaticities", "sRGB": "sRGB rendering intent",
    "iCCP": "ICC profile", "tEXt": "textual data",
    "zTXt": "compressed textual data", "iTXt": "international textual data",
    "bKGD": "background colour", "pHYs": "physical pixel dimensions",
    "sBIT": "significant bits", "sPLT": "suggested palette",
    "hIST": "palette histogram", "tIME": "last modification time",
    "eXIf": "Exif metadata", "oFFs": "image offset",
    "pCAL": "calibration of pixel values", "sCAL": "physical scale",
    "gIFg": "GIF graphic control", "gIFx": "GIF application data",
    "fRAc": "fractal parameters", "sTER": "stereo indicator",
    "acTL": "APNG animation control", "fcTL": "APNG frame control",
    "fdAT": "APNG frame data",
}


class PNGError(ValueError):
    """PNG 结构解析失败。"""


def _chunk_blob(ctype, payload):
    """打包一个 CRC 正确的 chunk(用于 --make-sample 与自测)。"""
    return (struct.pack(">I", len(payload)) + ctype + payload +
            struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF))


def walk(data):
    """遍历 PNG 全部 chunk，返回结果 dict；结构损坏抛 PNGError。"""
    if data[:8] != SIGNATURE:
        raise PNGError("bad PNG signature: %r" % bytes(data[:8]))
    chunks = []
    pos = 8
    while pos < len(data):
        if pos + 8 > len(data):
            raise PNGError("truncated: only %d byte(s) left for a chunk header at offset %d"
                           % (len(data) - pos, pos))
        length = int.from_bytes(data[pos:pos + 4], "big")
        ctype = data[pos + 4:pos + 8]
        for c in ctype:
            if not (65 <= c <= 90 or 97 <= c <= 122):
                raise PNGError("invalid chunk type %r at offset %d" % (bytes(ctype), pos))
        data_off = pos + 8
        end = data_off + length + 4
        if end > len(data):
            raise PNGError("chunk %r at offset %d overruns EOF (needs %d more bytes)"
                           % (bytes(ctype), pos, end - len(data)))
        payload = data[data_off:data_off + length]
        crc_stored = int.from_bytes(data[data_off + length:end], "big")
        code = ctype.decode("ascii")
        chunks.append({
            "index": len(chunks) + 1,
            "offset": pos,
            "length": length,
            "type": code,
            "data_offset": data_off,
            "ancillary": bool(ctype[0] & 0x20),
            "private": bool(ctype[1] & 0x20),
            "reserved_bit": bool(ctype[2] & 0x20),
            "safe_to_copy": bool(ctype[3] & 0x20),
            "crc_ok": crc_stored == (zlib.crc32(ctype + payload) & 0xFFFFFFFF),
            "description": PNG_TYPES.get(code, "unknown"),
        })
        pos = end
        if ctype == b"IEND":
            break
    return {
        "file_size": len(data),
        "signature_ok": True,
        "chunks": chunks,
        "iend_present": any(c["type"] == "IEND" for c in chunks),
        "trailing_bytes": len(data) - pos,
    }


def flags_text(chunk):
    parts = ["ancillary" if chunk["ancillary"] else "critical",
             "private" if chunk["private"] else "public"]
    if chunk["reserved_bit"]:
        parts.append("RESERVED-BIT-SET!")
    parts.append("safe-to-copy" if chunk["safe_to_copy"] else "unsafe-to-copy")
    return ",".join(parts)


def format_text(info):
    lines = [
        "file: %s (%d bytes)" % (info.get("path", "<memory>"), info["file_size"]),
        "   #    offset    length  type  flags                                    crc  description",
    ]
    critical = ancillary = 0
    idat_total = 0
    for c in info["chunks"]:
        if c["ancillary"]:
            ancillary += 1
        else:
            critical += 1
        if c["type"] == "IDAT":
            idat_total += c["length"]
        lines.append("%4d %9d %9d  %-5s %-38s %s  %s" % (
            c["index"], c["offset"], c["length"], c["type"], flags_text(c),
            "ok" if c["crc_ok"] else "BAD", c["description"]))
    lines.append("%d chunks (critical %d, ancillary %d); IDAT payload total %d bytes"
                 % (len(info["chunks"]), critical, ancillary, idat_total))
    if not info["iend_present"]:
        lines.append("warning: IEND chunk missing (file may be truncated)")
    if info["trailing_bytes"]:
        lines.append("warning: %d trailing byte(s) after IEND" % info["trailing_bytes"])
    bad = [c for c in info["chunks"] if not c["crc_ok"]]
    if bad:
        lines.append("warning: CRC mismatch in %s"
                     % ", ".join("#%d %s" % (c["index"], c["type"]) for c in bad))
    return "\n".join(lines)


def make_sample(width=8, height=8):
    """示例 PNG：IHDR + tEXt + 自定义辅助块 cuSt + IDAT + IEND。"""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = bytearray()
    for y in range(height):
        rows.append(0)  # filter type: none
        for x in range(width):
            rows += bytes(((x * 31 + y * 17) % 256,
                           (x * 13 + y * 7) % 256,
                           (x + y) % 256))
    return b"".join([
        SIGNATURE,
        _chunk_blob(b"IHDR", ihdr),
        _chunk_blob(b"tEXt", b"Comment\x00made by png-chunk-walker selftest"),
        _chunk_blob(b"cuSt", b"ancillary/private/safe-to-copy demo"),
        _chunk_blob(b"IDAT", zlib.compress(bytes(rows), 9)),
        _chunk_blob(b"IEND", b""),
    ])


def selftest():
    # 1) 正常遍历：5 个块，顺序与标志位正确
    info = walk(make_sample())
    types = [c["type"] for c in info["chunks"]]
    assert types == ["IHDR", "tEXt", "cuSt", "IDAT", "IEND"], types
    assert all(c["crc_ok"] for c in info["chunks"]), info
    cust = info["chunks"][2]
    assert cust["ancillary"] and cust["private"] and cust["safe_to_copy"], cust
    assert not cust["reserved_bit"], cust
    assert info["iend_present"] and info["trailing_bytes"] == 0, info
    print("  [ok] 5 chunks walked; cuSt flagged ancillary/private/safe-to-copy")

    # 2) CRC 破坏：不中断遍历，仅标注 BAD
    blob = bytearray(make_sample())
    blob[-1] ^= 0xFF  # IEND 的 CRC 最后一字节
    info = walk(bytes(blob))
    assert info["chunks"][-1]["crc_ok"] is False, info
    assert info["chunks"][0]["crc_ok"] is True, info
    print("  [ok] corrupted CRC reported as BAD without aborting")

    # 3) 坏签名 / 截断块必须报错
    for bad in (b"NG\x89" + b"\x00" * 10, make_sample()[:-20]):
        try:
            walk(bad)
        except PNGError:
            pass
        else:
            raise AssertionError("bad input accepted: %r" % bad[:8])
    print("  [ok] bad signature / truncated chunk rejected")

    # 4) 临时文件链路 + 文本/JSON 输出
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
        fh.write(make_sample())
        path = fh.name
    try:
        with open(path, "rb") as fh:
            info = walk(fh.read())
        text = format_text(dict(info, path=path))
        assert "IDAT" in text and "IEND" in text and "5 chunks" in text
        assert json.loads(json.dumps(info))["chunks"][0]["type"] == "IHDR"
    finally:
        os.unlink(path)
    print("  [ok] temp-file round-trip, text+json output")

    print("selftest PASS (4 checks)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="png-chunk-walker",
        description="按顺序列出 PNG 全部 chunk 的类型、长度与文件偏移, 标注关键/辅助/私有位")
    parser.add_argument("file", nargs="?", help=".png 文件路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--make-sample", metavar="OUT",
                        help="生成示例 PNG(含 tEXt 与自定义辅助块)到 OUT 后退出")
    parser.add_argument("--selftest", action="store_true", help="运行内置自测后退出")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.make_sample:
        blob = make_sample()
        with open(args.make_sample, "wb") as fh:
            fh.write(blob)
        print("wrote %d-byte sample PNG to %s" % (len(blob), args.make_sample))
        return 0
    if not args.file:
        parser.error("need a .png file (or --selftest / --make-sample)")
    try:
        with open(args.file, "rb") as fh:
            info = walk(fh.read())
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    except PNGError as exc:
        print("error: %s: %s" % (args.file, exc), file=sys.stderr)
        return 1
    info["path"] = args.file
    print(json.dumps(info, indent=2) if args.json else format_text(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
