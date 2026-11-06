#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aspect-ratio-match —— 计算宽高比并匹配最接近的常见比例

用途:
    读取图片的像素宽高 (解析 JPEG/PNG/GIF/BMP/TIFF/WEBP 的头部, 不解码像素),
    计算宽高比, 与常见比例 (1:1、5:4、4:3、3:2、5:3、16:10、16:9、21:9、2:1、32:9,
    自动覆盖竖版倒置) 匹配, 给出最接近的比例与偏差百分比:
        偏差% = |实际比 - 候选比| / 候选比 * 100   (横竖归一后比较)
    并按 --tolerance (默认 5%) 给出 MATCH / NO MATCH 判定。
    仅依赖 Python 标准库。

示例命令:
    python aspect-ratio-match.py photo.jpg
    python aspect-ratio-match.py screenshot.png --all
    python aspect-ratio-match.py clip.webp --tolerance 2.0

退出码: 0 成功; 1 无法读取尺寸/不支持; 2 命令行参数错误。
"""

import argparse
import math
import struct
import sys
from pathlib import Path

CANDIDATES = [
    ("1:1", 1, 1), ("5:4", 5, 4), ("4:3", 4, 3), ("3:2", 3, 2),
    ("5:3", 5, 3), ("16:10", 16, 10), ("16:9", 16, 9),
    ("21:9", 21, 9), ("2:1", 2, 1), ("32:9", 32, 9),
]
SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
               0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


class ToolError(Exception):
    """可预期的解析错误: 输出干净信息, 退出码 1。"""


def size_jpeg(data):
    n, pos = len(data), 2
    while pos + 4 <= n:
        if data[pos] != 0xFF:
            raise ToolError("corrupt JPEG marker stream")
        while pos < n and data[pos] == 0xFF:
            pos += 1
        if pos >= n:
            break
        marker = data[pos]
        pos += 1
        if marker == 0xD8 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if marker in (0xD9, 0xDA):
            raise ToolError("no SOF (start-of-frame) marker found")
        if pos + 2 > n:
            break
        seglen = struct.unpack_from(">H", data, pos)[0]
        if seglen < 2:
            break
        payload = data[pos + 2:min(pos + seglen, n)]
        pos += seglen
        if marker in SOF_MARKERS:
            if len(payload) < 5:
                raise ToolError("SOF segment too short")
            h, w = struct.unpack_from(">HH", payload, 1)
            return w, h, "JPEG (SOF{})".format(marker - 0xC0)
    raise ToolError("no SOF (start-of-frame) marker found")


def size_png(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ToolError("not a PNG")
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise ToolError("PNG IHDR chunk missing")
    w, h = struct.unpack_from(">II", data, 16)
    return w, h, "PNG (IHDR)"


def size_gif(data):
    if data[:4] != b"GIF8":
        raise ToolError("not a GIF")
    w, h = struct.unpack_from("<HH", data, 6)
    return w, h, "GIF ({})".format(data[:6].decode("ascii", "replace"))


def size_bmp(data):
    if data[:2] != b"BM" or len(data) < 26:
        raise ToolError("not a BMP")
    dib = struct.unpack_from("<I", data, 14)[0]
    if dib == 12:
        w, h = struct.unpack_from("<HH", data, 18)
    else:
        w, h = struct.unpack_from("<ii", data, 18)
    return w, abs(h), "BMP (DIB {} bytes)".format(dib)


def size_tiff(data):
    e = {b"II": "<", b"MM": ">"}.get(data[:2])
    if e is None:
        raise ToolError("not a TIFF")
    magic, first = struct.unpack_from(e + "HI", data, 2)
    if magic != 42:
        raise ToolError("bad TIFF magic")
    seen = set()
    while first and first not in seen:
        seen.add(first)
        try:
            count = struct.unpack_from(e + "H", data, first)[0]
        except struct.error:
            break
        if not (0 < count <= 1024):
            break
        w = h = None
        for i in range(count):
            erel = first + 2 + 12 * i
            tag, typ, cnt = struct.unpack_from(e + "HHI", data, erel)
            if tag in (0x0100, 0x0101) and cnt == 1 and typ in (3, 4):
                val = struct.unpack_from(e + ("H" if typ == 3 else "I"), data, erel + 8)[0]
                if tag == 0x0100:
                    w = val
                else:
                    h = val
        if w and h:
            return w, h, "TIFF ({}-endian)".format("little" if e == "<" else "big")
        try:
            first = struct.unpack_from(e + "I", data, first + 2 + 12 * count)[0]
        except struct.error:
            break
    raise ToolError("ImageWidth/ImageLength not found in IFD0")


def size_webp(data):
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ToolError("not a WEBP (RIFF/WEBP)")
    n, pos = len(data), 12
    while pos + 8 <= n:
        fourcc = data[pos:pos + 4]
        sz = struct.unpack_from("<I", data, pos + 4)[0]
        payload = data[pos + 8:min(pos + 8 + sz, n)]
        if fourcc == b"VP8X" and len(payload) >= 10:
            w = 1 + int.from_bytes(payload[4:7], "little")
            h = 1 + int.from_bytes(payload[7:10], "little")
            return w, h, "WEBP (VP8X)"
        if fourcc == b"VP8 " and len(payload) >= 10 and payload[3:6] == b"\x9d\x01\x2a":
            w = struct.unpack_from("<H", payload, 6)[0] & 0x3FFF
            h = struct.unpack_from("<H", payload, 8)[0] & 0x3FFF
            return w, h, "WEBP (VP8 lossy)"
        if fourcc == b"VP8L" and len(payload) >= 5 and payload[0] == 0x2F:
            bits = struct.unpack_from("<I", payload, 1)[0]
            w = (bits & 0x3FFF) + 1
            h = ((bits >> 14) & 0x3FFF) + 1
            return w, h, "WEBP (VP8L lossless)"
        pos += 8 + sz + (sz & 1)
    raise ToolError("no WEBP size chunk (VP8X/VP8/VP8L)")


DETECTORS = [
    (b"\xff\xd8", size_jpeg),
    (b"\x89PNG", size_png),
    (b"GIF8", size_gif),
    (b"BM", size_bmp),
    (b"II", size_tiff),
    (b"MM", size_tiff),
    (b"RIFF", size_webp),
]


def detect_size(data):
    for magic, fn in DETECTORS:
        if data[:len(magic)] == magic:
            return fn(data)
    raise ToolError("unsupported format (supported: JPEG, PNG, GIF, BMP, TIFF, WEBP)")


def rank(w, h):
    """返回 (实际比值, [(偏差%, 标签, 候选值), ...] 按偏差升序)。"""
    ratio = w / h
    norm = min(ratio, 1.0 / ratio)
    scored = []
    for label, num, den in CANDIDATES:
        cand = num / den
        cnorm = min(cand, 1.0 / cand)
        dev = abs(norm - cnorm) / cnorm * 100.0
        scored.append((dev, label, cand))
    scored.sort(key=lambda item: item[0])
    return ratio, scored


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="aspect-ratio-match",
        description="Match an image's aspect ratio against common ratios and report the deviation.",
    )
    ap.add_argument("file", help="image file (JPEG/PNG/GIF/BMP/TIFF/WEBP)")
    ap.add_argument("--all", action="store_true", help="list every candidate ratio sorted by deviation")
    ap.add_argument("--tolerance", type=float, default=5.0, metavar="PCT",
                    help="max deviation in percent to call it a match (default: 5.0)")
    args = ap.parse_args(argv)

    path = Path(args.file)
    try:
        data = path.read_bytes()
    except OSError as exc:
        print("error: cannot read {}: {}".format(path, exc), file=sys.stderr)
        return 1
    try:
        w, h, how = detect_size(data)
    except ToolError as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 1
    if w <= 0 or h <= 0:
        print("error: nonsensical dimensions {}x{}".format(w, h), file=sys.stderr)
        return 1

    ratio, scored = rank(w, h)
    dev, label, _ = scored[0]
    orientation = "portrait" if h > w else ("square" if w == h else "landscape")
    g = math.gcd(w, h)
    exact = dev < 0.005
    verdict = "MATCH" if dev <= args.tolerance else "NO MATCH"
    shown = label if w >= h else "{}:{} (portrait)".format(label.split(":")[1], label.split(":")[0])

    print("file   : {}".format(path))
    print("format : {}".format(how))
    print("size   : {} x {} ({}, reduced {}:{})".format(w, h, orientation, w // g, h // g))
    print("ratio  : {:.4f}".format(ratio))
    print("match  : {}  deviation {:.2f}%{}  -> {} (tolerance {:.1f}%)".format(
        shown, dev, " (exact)" if exact else "", verdict, args.tolerance))
    if args.all:
        print()
        print("     dev  candidate")
        for d, lab, cand in scored:
            mark = "  <-" if lab == label else ""
            print("  {:7.3f}%  {:<6} (= {:.4f}){}".format(d, lab, cand, mark))
    return 0


if __name__ == "__main__":
    sys.exit(main())
