#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JPEG2000 尺寸读取器(jp2-size-read) —— 解析 JP2 盒结构或裸码流的 SIZ 段，输出宽高与分量数。

用途:
    支持两种输入：
    1. JP2 容器(以签名盒 jP 开头)：遍历顶层盒，从 jp2h 内的 ihdr 盒读取
       宽/高/分量数/位深，附带 colr 颜色空间、盒列表，并对 jp2c 内嵌码流的
       SIZ 做交叉校验；
    2. 裸 JPEG 2000 码流(以 SOC=FF4F 开头)：定位 SIZ(FF51) 段，输出
       Xsiz-XOsiz/Ysiz-YOsiz 得到的宽高与 Csiz 分量数(含逐分量位深/子采样)。
    两种都识别不了时可用 --scan 在全文件里搜索结构。

用法:
    python jp2-size-read.py <file.jp2|file.j2k> [--json] [--scan]
    python jp2-size-read.py --make-sample <out.jp2|.j2k>   生成示例文件
    python jp2-size-read.py --selftest                     构造示例输入并自校验

示例:
    python jp2-size-read.py image.jp2
    python jp2-size-read.py stream.j2k --scan
    python jp2-size-read.py image.jp2 --json
    python jp2-size-read.py --selftest

退出码: 0=成功; 1=解析失败/不是 JPEG 2000; 2=命令行用法错误。
仅使用 Python 标准库(argparse/json/struct/tempfile/os)。
"""

import argparse
import json
import os
import struct
import sys
import tempfile

JP2_SIGNATURE = b"\x00\x00\x00\x0cjP  \x0d\x0a\x87\x0a"
MARKER_SOC = 0xFF4F
MARKER_SIZ = 0xFF51
MARKER_SOD = 0xFF93
MARKER_EOC = 0xFFD9

COLOUR_ENUM = {16: "sRGB", 17: "greyscale", 18: "sYCC", 24: "e-sRGB"}


class JP2Error(ValueError):
    """JPEG 2000 解析失败。"""


def walk_boxes(data, start=0, end=None):
    """遍历 [start, end) 内的 JPEG 2000 盒，返回 [{offset,type,length,header}]。"""
    if end is None:
        end = len(data)
    boxes = []
    pos = start
    while pos < end:
        if pos + 8 > end:
            raise JP2Error("truncated box header at offset %d" % pos)
        length = int.from_bytes(data[pos:pos + 4], "big")
        btype = data[pos + 4:pos + 8]
        hdr = 8
        if length == 1:
            if pos + 16 > end:
                raise JP2Error("XL (length=1) box at offset %d truncated" % pos)
            length = int.from_bytes(data[pos + 8:pos + 16], "big")
            hdr = 16
        elif length == 0:
            length = end - pos
        if length < hdr or pos + length > end:
            raise JP2Error("box %r at offset %d overruns its container (len=%d)"
                           % (bytes(btype), pos, length))
        boxes.append({"offset": pos, "type": btype.decode("latin-1"),
                      "length": length, "header": hdr})
        pos += length
    return boxes


def parse_ihdr(data, box):
    start = box["offset"] + box["header"]
    payload = data[start:box["offset"] + box["length"]]
    if len(payload) < 14:
        raise JP2Error("ihdr box payload too short (%d bytes)" % len(payload))
    height, width, ncomp, bpc, compression, unknown, ipr = \
        struct.unpack_from(">IIHBBBB", payload, 0)
    return {
        "width": width,
        "height": height,
        "components": ncomp,
        "bit_depth": (bpc & 0x7F) + 1,
        "signed": bool(bpc & 0x80),
        "compression": compression,
        "unknown_components": unknown,
        "ipr": ipr,
    }


def parse_colr(data, box):
    start = box["offset"] + box["header"]
    payload = data[start:box["offset"] + box["length"]]
    if len(payload) < 3:
        return None
    meth, _prec, _approx = payload[0], payload[1], payload[2]
    if meth == 1 and len(payload) >= 7:
        enum = int.from_bytes(payload[3:7], "big")
        return {"meth": 1, "enum": enum,
                "name": COLOUR_ENUM.get(enum, "enum %d" % enum)}
    if meth == 2:
        return {"meth": 2, "enum": None, "name": "restricted ICC profile"}
    return {"meth": meth, "enum": None, "name": "meth %d" % meth}


def parse_siz(payload):
    if len(payload) < 36:
        raise JP2Error("SIZ segment too short (%d bytes, need >= 36)" % len(payload))
    (rsiz, xsiz, ysiz, xosiz, yosiz,
     xtsiz, ytsiz, xtosiz, ytosiz, csiz) = struct.unpack(">H8IH", payload[:36])
    if xsiz <= xosiz or ysiz <= yosiz:
        raise JP2Error("degenerate image extent: Xsiz=%d-XOsiz=%d, Ysiz=%d-YOsiz=%d"
                       % (xsiz, xosiz, ysiz, yosiz))
    if csiz == 0 or csiz > 16384:
        raise JP2Error("implausible component count %d" % csiz)
    if len(payload) < 36 + 3 * csiz:
        raise JP2Error("SIZ too short for %d components" % csiz)
    comps = []
    for i in range(csiz):
        ssiz, xr, yr = struct.unpack_from(">BBB", payload, 36 + 3 * i)
        if xr == 0 or yr == 0:
            raise JP2Error("component %d has zero subsampling factor" % i)
        comps.append({"precision": (ssiz & 0x7F) + 1,
                      "signed": bool(ssiz & 0x80),
                      "xrsiz": xr, "yrsiz": yr})
    return {
        "width": xsiz - xosiz,
        "height": ysiz - yosiz,
        "components": csiz,
        "xsiz": xsiz, "ysiz": ysiz, "xosiz": xosiz, "yosiz": yosiz,
        "xtsiz": xtsiz, "ytsiz": ytsiz, "rsiz": rsiz,
        "comps": comps,
    }


def parse_codestream(data):
    if data[:2] != b"\xff\x4f":
        raise JP2Error("codestream must start with SOC (FF 4F), got %r" % bytes(data[:2]))
    pos = 2
    while pos + 2 <= len(data):
        marker = int.from_bytes(data[pos:pos + 2], "big")
        if marker in (MARKER_EOC, MARKER_SOD):
            break
        if marker == MARKER_SOC:
            pos += 2
            continue
        if pos + 4 > len(data):
            raise JP2Error("truncated marker-segment header at offset %d" % pos)
        seg_len = int.from_bytes(data[pos + 2:pos + 4], "big")
        if seg_len < 2 or pos + 2 + seg_len > len(data):
            raise JP2Error("bad marker-segment length %d at offset %d" % (seg_len, pos))
        if marker == MARKER_SIZ:
            return parse_siz(data[pos + 4:pos + 2 + seg_len])
        pos += 2 + seg_len
    raise JP2Error("no SIZ (FF 51) marker found in codestream")


def parse_jp2(data):
    if data[:12] != JP2_SIGNATURE:
        raise JP2Error("missing JP2 signature box")
    boxes = walk_boxes(data)
    ihdr = colr = codestream = None
    warnings = []
    for box in boxes:
        if box["type"] == "jp2h":
            for sub in walk_boxes(data, box["offset"] + box["header"],
                                  box["offset"] + box["length"]):
                if sub["type"] == "ihdr" and ihdr is None:
                    ihdr = parse_ihdr(data, sub)
                elif sub["type"] == "colr" and colr is None:
                    colr = parse_colr(data, sub)
        elif box["type"] in ("jp2c", "jpx ", "j2k "):
            start = box["offset"] + box["header"]
            payload = data[start:box["offset"] + box["length"]]
            if payload[:2] == b"\xff\x4f":
                try:
                    codestream = parse_codestream(payload)
                except JP2Error as exc:
                    warnings.append("embedded codestream: %s" % exc)
            else:
                warnings.append("box %s does not start with SOC" % box["type"])
    if ihdr is None:
        raise JP2Error("no ihdr box inside jp2h (bare codestream? it should start with FF 4F)")
    if codestream and (codestream["width"], codestream["height"],
                       codestream["components"]) != (ihdr["width"], ihdr["height"],
                                                     ihdr["components"]):
        warnings.append("codestream SIZ %dx%dx%d disagrees with ihdr %dx%dx%d"
                        % (codestream["width"], codestream["height"],
                           codestream["components"], ihdr["width"],
                           ihdr["height"], ihdr["components"]))
    return {
        "kind": "jp2-container",
        "boxes": boxes,
        "ihdr": ihdr,
        "colr": colr,
        "codestream": codestream,
        "warnings": warnings,
        "width": ihdr["width"],
        "height": ihdr["height"],
        "components": ihdr["components"],
    }


def parse(data):
    if data[:12] == JP2_SIGNATURE:
        return parse_jp2(data)
    if data[:2] == b"\xff\x4f":
        info = parse_codestream(data)
        info["kind"] = "raw-codestream"
        return info
    raise JP2Error("neither JP2 signature box nor SOC marker found (try --scan)")


def scan(data):
    """在全文件中搜索 JPEG 2000 结构（SOC+SIZ 相邻，或 JP2 签名盒）。"""
    for needle in (JP2_SIGNATURE, b"\xff\x4f\xff\x51"):
        at = data.find(needle)
        if at < 0:
            continue
        try:
            if needle == JP2_SIGNATURE:
                info = parse_jp2(data[at:])
            else:
                info = parse_codestream(data[at:])
                info["kind"] = "raw-codestream"
        except JP2Error:
            continue
        info["found_at_offset"] = at
        return info
    raise JP2Error("--scan found no parsable JPEG 2000 structure")


def format_text(info):
    lines = [
        "file: %s" % info.get("path", "<memory>"),
        "kind: %s" % info["kind"],
        "width x height: %d x %d" % (info["width"], info["height"]),
        "components:     %d" % info["components"],
    ]
    if info.get("found_at_offset") is not None:
        lines.append("found at:       offset %d (--scan)" % info["found_at_offset"])
    if info["kind"] == "jp2-container":
        ihdr = info["ihdr"]
        lines.append("bit depth:      %d-bit %s (ihdr bpc)"
                     % (ihdr["bit_depth"], "signed" if ihdr["signed"] else "unsigned"))
        if info["colr"]:
            lines.append("colour:         %s" % info["colr"]["name"])
        lines.append("boxes:          " + ", ".join(
            "%s@%d(%d)" % (b["type"], b["offset"], b["length"]) for b in info["boxes"]))
        if info["codestream"]:
            cs = info["codestream"]
            lines.append("codestream:     SIZ %dx%d, %d component(s)"
                         % (cs["width"], cs["height"], cs["components"]))
    else:
        lines.append("image offset:   (%d, %d)  tile %dx%d"
                     % (info["xosiz"], info["yosiz"], info["xtsiz"], info["ytsiz"]))
        lines.append("components:     " + "; ".join(
            "%d-bit%s, subsample %dx%d" % (c["precision"], " signed" if c["signed"] else "",
                                           c["xrsiz"], c["yrsiz"])
            for c in info["comps"]))
    for w in info.get("warnings", []):
        lines.append("warning: %s" % w)
    return "\n".join(lines)


def _box(btype, payload):
    return struct.pack(">I", 8 + len(payload)) + btype + payload


def make_codestream(width, height, comps=3, xosiz=0, yosiz=0):
    """构造最小合法码流：SOC + SIZ + EOC（无熵编码数据）。"""
    payload = struct.pack(">H8IH", 0, width, height, xosiz, yosiz,
                          width, height, 0, 0, comps)
    payload += bytes((7, 1, 1)) * comps
    return b"\xff\x4f" + struct.pack(">HH", MARKER_SIZ, 2 + len(payload)) + payload + b"\xff\xd9"


def make_sample(width=320, height=240, comps=3):
    """构造最小合法 JP2 容器：签名盒 + ftyp + jp2h(ihdr+colr) + jp2c。"""
    sig = JP2_SIGNATURE
    ftyp = _box(b"ftyp", b"jp2 \x00\x00\x00\x00jp2 ")
    ihdr = _box(b"ihdr", struct.pack(">IIHBBBB", height, width, comps, 7, 7, 0, 0))
    colr = _box(b"colr", bytes((1, 0, 0)) + struct.pack(">I", 16))
    jp2h = _box(b"jp2h", ihdr + colr)
    jp2c = _box(b"jp2c", make_codestream(width, height, comps))
    return sig + ftyp + jp2h + jp2c


def selftest():
    # 1) JP2 容器
    info = parse(make_sample())
    assert info["kind"] == "jp2-container"
    assert (info["width"], info["height"], info["components"]) == (320, 240, 3), info
    assert info["ihdr"]["bit_depth"] == 8 and not info["ihdr"]["signed"], info
    assert info["colr"]["name"] == "sRGB", info
    assert info["codestream"] and not info["warnings"], info
    print("  [ok] JP2 container: 320x240, 3 components, sRGB, jp2c cross-checked")

    # 2) 裸码流（带图像偏移 XOsiz/YOsiz）
    info = parse(make_codestream(640, 240, comps=3, xosiz=8, yosiz=4))
    assert (info["width"], info["height"]) == (632, 236), info
    assert info["components"] == 3 and info["comps"][0]["precision"] == 8, info
    print("  [ok] raw codestream SIZ: 640x240 minus offset -> 632x236")

    # 3) --scan 兜底
    info = scan(b"\xde\xad\xbe\xef" * 4 + make_sample())
    assert info["found_at_offset"] == 16 and info["width"] == 320, info
    print("  [ok] --scan locates JP2 structure at offset 16")

    # 4) 垃圾输入 / 无 SIZ 的码流必须报错
    for bad in (b"garbage" * 8, b"\xff\x4f\xff\x52\x00\x04"):
        try:
            parse(bad)
        except JP2Error:
            pass
        else:
            raise AssertionError("bad input accepted: %r" % bad[:8])
    print("  [ok] garbage and SIZ-less codestream rejected")

    # 5) 临时文件链路 + 文本/JSON 输出
    with tempfile.NamedTemporaryFile(suffix=".jp2", delete=False) as fh:
        fh.write(make_sample())
        path = fh.name
    try:
        with open(path, "rb") as fh:
            info = parse(fh.read())
        assert "320 x 240" in format_text(dict(info, path=path))
        assert json.loads(json.dumps(info))["components"] == 3
    finally:
        os.unlink(path)
    print("  [ok] temp-file round-trip, text+json output")

    print("selftest PASS (5 checks)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="jp2-size-read",
        description="解析 JP2 盒结构或裸码流 SIZ 段, 输出宽高与分量数")
    parser.add_argument("file", nargs="?", help=".jp2/.j2k 文件路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--scan", action="store_true",
                        help="常规识别失败时全文件搜索 JPEG 2000 结构")
    parser.add_argument("--make-sample", metavar="OUT",
                        help="生成示例文件(扩展名 .j2k/.jpc/.j2c 为裸码流, 其余为 JP2 容器)")
    parser.add_argument("--selftest", action="store_true", help="运行内置自测后退出")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.make_sample:
        low = args.make_sample.lower()
        if low.endswith((".j2k", ".jpc", ".j2c")):
            blob, kind = make_codestream(640, 240, comps=3), "raw codestream"
        else:
            blob, kind = make_sample(), "JP2 container"
        with open(args.make_sample, "wb") as fh:
            fh.write(blob)
        print("wrote %d-byte sample %s to %s" % (len(blob), kind, args.make_sample))
        return 0
    if not args.file:
        parser.error("need a .jp2/.j2k file (or --selftest / --make-sample)")
    try:
        with open(args.file, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    try:
        try:
            info = parse(data)
        except JP2Error:
            if not args.scan:
                raise
            info = scan(data)
    except JP2Error as exc:
        print("error: %s: %s" % (args.file, exc), file=sys.stderr)
        return 1
    info["path"] = args.file
    print(json.dumps(info, indent=2) if args.json else format_text(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
