#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""photoshop-irb-read —— 读取 JPEG APP13 中的 Photoshop 图像资源 (IRB / 8BIM)

用途:
    解析 JPEG 的 APP13 段 ("Photoshop 3.0\\0") 中的 8BIM 图像资源块,
    逐块列出资源 ID、资源名称与数据长度, 并展开关键内容:
    分辨率 (0x03ED)、缩略图 (0x0409/0x040C)、标题 (0x03F0)、URL (0x040B)、
    版权标志 (0x040A)、版本信息 (0x0421)、像素纵横比 (0x0424)、
    IPTC/XMP/EXIF/ICC 的存在性等。
    块名编码逐块自动判别, 同时支持两种写法:
      - Adobe 规范的 Pascal 串: 1 字节长度 + 内容, 名称字段整体补齐到偶数
        (PSD 文件格式与 TIFF tag 34377 即此写法);
      - JPEG APP13 实际输出的 2 字节长度前缀变体 (内容可能自带 Pascal 长度字节)。
    也接受以 '8BIM' 或 'Photoshop 3.0\\0' 开头的原始资源流 (--raw 或自动识别)。
    仅依赖 Python 标准库。

示例命令:
    python photoshop-irb-read.py photo.jpg
    python photoshop-irb-read.py resources.8bim --raw

退出码: 0 成功; 1 未找到 APP13/资源块或无法解析; 2 命令行参数错误。
"""

import argparse
import struct
import sys
from pathlib import Path

PS13_SIG = b"Photoshop 3.0\x00"
BLOCK_SIGS = (b"8BIM", b"PHUT", b"DCSR", b"AgHg", b"MeSa")

RESOURCE_NAMES = {
    0x03E9: "Macintosh print manager info",
    0x03EB: "Macintosh page format",
    0x03ED: "ResolutionInfo",
    0x03EE: "Alpha channel names",
    0x03EF: "DisplayInfo",
    0x03F0: "Caption (Pascal string)",
    0x03F1: "Border information",
    0x03F2: "Background color",
    0x03F3: "Print flags",
    0x03F4: "Grayscale/multichannel halftoning",
    0x03F5: "Color halftoning",
    0x03F6: "Duotone halftoning",
    0x03F7: "Grayscale/multichannel transfer function",
    0x03F8: "Color transfer functions",
    0x03F9: "Duotone transfer functions",
    0x03FA: "Duotone image info",
    0x03FB: "Effective black & white values",
    0x03FD: "EPS options",
    0x03FE: "Quick Mask info",
    0x0400: "Layer state information",
    0x0401: "Working path (unnamed)",
    0x0402: "Layers group information",
    0x0404: "IPTC-NAA record",
    0x0405: "Image mode for raw format files",
    0x0406: "JPEG quality",
    0x0408: "Grid & guides information",
    0x0409: "Thumbnail (PS 4.0, BGR)",
    0x040A: "Copyright flag",
    0x040B: "URL",
    0x040C: "Thumbnail (PS 5.0, RGB)",
    0x040D: "Global angle",
    0x040E: "Color samplers",
    0x040F: "ICC profile (obsolete, now APP2)",
    0x0410: "Layer information",
    0x0421: "Version info",
    0x0422: "EXIF data 1",
    0x0423: "EXIF data 2",
    0x0424: "XMP metadata",
    0x0425: "IPTC digest",
    0x0426: "Print scale",
    0x0428: "Pixel aspect ratio",
    0x042D: "Layer selection ID",
}


class ToolError(Exception):
    """可预期的解析错误: 输出干净信息, 退出码 1。"""


def be16(buf, off):
    return struct.unpack_from(">H", buf, off)[0]


def be32(buf, off):
    return struct.unpack_from(">I", buf, off)[0]


def app13_payloads(data):
    """扫描 JPEG 标记流, 收集 APP13 "Photoshop 3.0" 段的载荷。"""
    payloads = []
    n = len(data)
    pos = 2
    while pos + 4 <= n:
        if data[pos] != 0xFF:
            break
        while pos < n and data[pos] == 0xFF:
            pos += 1
        if pos >= n:
            break
        marker = data[pos]
        pos += 1
        if marker == 0xD8 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if marker in (0xD9, 0xDA):
            break
        if pos + 2 > n:
            break
        seglen = be16(data, pos)
        if seglen < 2:
            break
        payload = data[pos + 2:min(pos + seglen, n)]
        pos += seglen
        if marker == 0xED and payload[:14] == PS13_SIG:
            payloads.append(payload[14:])
    return payloads


def _decode_name_a(raw):
    """JPEG 2 字节前缀变体的名字解码; 内容常为 Pascal 串 (长度字节 + 正文, 可带补齐)。"""
    if not raw:
        return ""
    plen = raw[0]
    # 首字节 = 正文长度、正文无 NUL、其后全是 NUL 补齐时, 按 Pascal 串解
    if plen <= len(raw) - 1 and b"\x00" not in raw[1:1 + plen] and not any(raw[1 + plen:]):
        text = raw[1:1 + plen]
        try:
            return text.decode("ascii")
        except UnicodeDecodeError:
            return text.decode("latin-1")
    s = raw.split(b"\x00", 1)[0]
    try:
        return s.decode("ascii")
    except UnicodeDecodeError:
        return s.decode("latin-1")


def _decode_name_b(raw):
    """Adobe Pascal 名字解码: 内容即名字本身。"""
    s = raw.split(b"\x00", 1)[0]
    try:
        return s.decode("ascii")
    except UnicodeDecodeError:
        return s.decode("latin-1")


def pascal_text(body, off=0):
    """读 1 字节长度前缀的 Pascal 字符串, 返回 (text, next_off)。"""
    if off >= len(body):
        return "", off
    n = body[off]
    end = min(off + 1 + n, len(body))
    text = body[off + 1:end].decode("latin-1", "replace")
    return text, end


def _name_candidate(stream, pos, n, layout):
    """在 pos 处按指定块名编码解释块头, 返回候选 dict; size 字段读不出则返回 None。

    'A' (JPEG APP13, Photoshop 实际输出): 2 字节前缀 P + P 字节名字,
        P 为奇数时名字后再补 1 字节; 名字内容可能自带 Pascal 长度字节。
    'B' (Adobe 规范, PSD/TIFF tag 34377 同): 1 字节 Pascal 长度 L + L 字节名字,
        (1+L) 为奇数时补 1 字节, 名称字段整体为偶数; 空名为两个 0 字节。
    """
    if layout == "A":
        plen = be16(stream, pos + 6) & 0x7FFF
        field_len = 2 + plen + (plen & 1)
        name_raw = bytes(stream[pos + 8:pos + 8 + plen])
    else:
        plen = stream[pos + 6]
        field_len = 1 + plen + ((1 + plen) & 1)
        name_raw = bytes(stream[pos + 7:pos + 7 + plen])
    size_off = pos + 6 + field_len
    if size_off + 4 > n:
        return None
    size = be32(stream, size_off)
    body_off = size_off + 4
    truncated = body_off + size > n
    block_len = (n - pos) if truncated else (size_off - pos) + 4 + size + (size & 1)
    return {"layout": layout, "name_raw": name_raw, "size": size,
            "body_off": body_off, "truncated": truncated, "block_len": block_len}


def parse_blocks(stream):
    """解析连续的图像资源块。每块对两种块名编码各求一个候选,
    以"块尾恰为下一块签名或流末尾"为契合度自动判别 (真正歧义时偏向 JPEG 约定)。"""
    blocks = []
    warnings = []
    pos = 0
    n = len(stream)
    while pos + 12 <= n:
        signature = stream[pos:pos + 4]
        if signature not in BLOCK_SIGS:
            warnings.append("stopped at offset {}: signature {!r} is not an image resource block".format(pos, bytes(signature)))
            break
        rid = be16(stream, pos + 4)
        strict, partial = [], []
        for layout in ("A", "B"):
            cand = _name_candidate(stream, pos, n, layout)
            if cand is None:
                continue
            (partial if cand["truncated"] else strict).append(cand)
        pool = strict or partial
        if not pool:
            warnings.append("truncated or corrupt block header at offset {} "
                            "(tried JPEG 2-byte-prefix and Adobe Pascal name layouts)".format(pos))
            break

        def clean_fit(cand):
            nxt = pos + cand["block_len"]
            return nxt == n or stream[nxt:nxt + 4] in BLOCK_SIGS

        perfect = [c for c in pool if clean_fit(c)]
        if len(perfect) == 1:
            chosen = perfect[0]
        elif perfect:
            chosen = perfect[0] if perfect[0]["layout"] == "A" else perfect[1]
        else:
            chosen = pool[0]
        truncated = bool(chosen["truncated"])
        if truncated:
            warnings.append("block 0x{:04X} data truncated (declared {} bytes, got {})".format(
                rid, chosen["size"], n - chosen["body_off"]))
        if chosen["layout"] == "A":
            name = _decode_name_a(chosen["name_raw"])
        else:
            name = _decode_name_b(chosen["name_raw"])
        body = stream[chosen["body_off"]:min(chosen["body_off"] + chosen["size"], n)]
        pos += chosen["block_len"]
        blocks.append({
            "sig": signature.decode("ascii", "replace"),
            "id": rid,
            "name": name,
            "size": chosen["size"],
            "body": body,
            "truncated": truncated,
        })
        if truncated:
            break
    return blocks, warnings


def describe(rid, body):
    """按资源 ID 展开关键内容, 返回行列表。"""
    lines = []
    if rid == 0x03ED and len(body) >= 16:
        hres, hunit, wunit, vres, vunit, hunit2 = struct.unpack(">iHHiHH", body[:16])
        unit = "ppi" if hunit == 1 else ("ppcm" if hunit == 2 else "unit{}".format(hunit))
        lines.append("resolution      : {:.2f} x {:.2f} {}".format(hres / 65536.0, vres / 65536.0, unit))
        units = {1: "inches", 2: "cm", 3: "points", 4: "picas", 5: "columns"}
        lines.append("print size unit : {} x {}".format(units.get(wunit, wunit), units.get(hunit2, hunit2)))
    elif rid in (0x03F0, 0x040B) and body:
        text, _ = pascal_text(body)
        lines.append("text            : {!r}".format(text))
    elif rid == 0x03EE and body:
        names, off = [], 0
        while off < len(body) and len(names) < 64:
            text, off = pascal_text(body, off)
            names.append(text)
        lines.append("alpha channels  : {}".format(names))
    elif rid == 0x040A and body:
        lines.append("copyrighted     : {}".format("yes" if body[0] else "no"))
    elif rid == 0x0400 and len(body) >= 2:
        lines.append("active layer #  : {}".format(be16(body, 0)))
    elif rid in (0x0409, 0x040C) and len(body) >= 28:
        fmt, tw, th, wb, total, comp, depth, planes = struct.unpack(">IIIIIIHH", body[:28])
        kind = {0: "raw RGB", 1: "JPEG"}.get(fmt, "format {}".format(fmt))
        lines.append("thumbnail       : {}, {}x{}, depth={}, planes={}, compressed={} bytes".format(kind, tw, th, depth, planes, comp))
    elif rid == 0x0421 and len(body) >= 5:
        version = be32(body, 0)
        has_merged = body[4]
        off = 5
        fields = []
        for label in ("writer", "reader"):
            if off + 4 > len(body):
                break
            ln = be32(body, off)
            off += 4
            fields.append("{}={!r}".format(label, body[off:off + ln].decode("ascii", "replace")))
            off += ln
        if off + 4 <= len(body):
            fields.append("fileVersion={}".format(be32(body, off)))
        lines.append("version         : v{}, merged={}, {}".format(version, bool(has_merged), ", ".join(fields)))
    elif rid == 0x0424 and len(body) >= 8:
        ver, ratio = struct.unpack(">Ii", body[:8])
        lines.append("aspect ratio    : {:.4f} (version {})".format(ratio / 65536.0, ver))
    elif rid == 0x0404:
        lines.append("note            : IPTC-IIM dataset ({} bytes, not expanded here)".format(len(body)))
    elif rid in (0x0422, 0x0423):
        lines.append("note            : embedded EXIF block ({} bytes)".format(len(body)))
    elif rid == 0x040F:
        lines.append("note            : ICC profile ({} bytes)".format(len(body)))
    elif rid == 0x0424:
        lines.append("note            : XMP packet ({} bytes{})".format(len(body), ", <x:xmpmeta> detected" if b"<x:xmpmeta" in body else ""))
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="photoshop-irb-read",
        description='List 8BIM image resource blocks in a JPEG APP13 ("Photoshop 3.0") segment.',
    )
    ap.add_argument("file", help="JPEG file, or a raw 8BIM resource stream")
    ap.add_argument("--raw", action="store_true", help="treat input as a raw IRB payload even if it does not look like one")
    args = ap.parse_args(argv)

    path = Path(args.file)
    try:
        data = path.read_bytes()
    except OSError as exc:
        print("error: cannot read {}: {}".format(path, exc), file=sys.stderr)
        return 1

    streams = []
    if not args.raw and data[:2] == b"\xff\xd8":
        streams = app13_payloads(data)
        source = 'JPEG APP13 ("Photoshop 3.0"), {} segment(s)'.format(len(streams))
    elif data[:14] == PS13_SIG:
        streams = [data[14:]]
        source = "raw IRB stream (Photoshop 3.0 header stripped)"
    elif args.raw or data[:4] in BLOCK_SIGS:
        streams = [data]
        source = "raw IRB stream"
    else:
        print("error: not a JPEG and not a raw 8BIM stream (try --raw)", file=sys.stderr)
        return 1

    if not streams:
        print('error: no APP13 ("Photoshop 3.0") segment found in this JPEG', file=sys.stderr)
        return 1

    blocks, warnings = [], []
    for stream in streams:
        got, warn = parse_blocks(stream)
        blocks.extend(got)
        warnings.extend(warn)

    if not blocks:
        print("error: no 8BIM image resource blocks found", file=sys.stderr)
        return 1

    print("file    : {}".format(path))
    print("source  : {}".format(source))
    print("blocks  : {}".format(len(blocks)))
    for warn in warnings:
        print("warning : {}".format(warn))
    print()
    for idx, blk in enumerate(blocks, 1):
        rname = RESOURCE_NAMES.get(blk["id"], "Unknown / proprietary")
        flag = "  [TRUNCATED]" if blk["truncated"] else ""
        print("[{}] {}  id=0x{:04X} ({})  {}".format(idx, blk["sig"], blk["id"], blk["id"], rname))
        print('    name="{}"  size={} bytes{}'.format(blk["name"], blk["size"], flag))
        for line in describe(blk["id"], blk["body"]):
            print("    " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
