#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TIFF IFD 摘要 —— 解析 TIFF 字节序与 IFD 链, 输出核心标签摘要。

读取文件头(字节序 II/MM、魔数 42、首个 IFD 偏移), 沿 next-IFD 指针
遍历整条 IFD 链(带环路保护), 对每个 IFD 输出: 宽度、高度、位深、
压缩算法、光度解释、每像素样本数、每条带行数、条带偏移/字节数、
X/Y 分辨率与分辨率单位。仅支持经典 TIFF(魔数 42), BigTIFF(43) 明确报错。

用法:
    python tiff-ifd-summary.py <文件.tif> [--json]

示例:
    python tiff-ifd-summary.py sample.tif
    python tiff-ifd-summary.py sample.tif --json

退出码: 0 = 解析成功; 1 = 不是 TIFF / 结构损坏。
仅使用 Python 标准库, 需 Python 3.7+。
"""

import argparse
import json
import struct
import sys

TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8,
              11: 4, 12: 8, 13: 4}
TYPE_NAMES = {1: "BYTE", 2: "ASCII", 3: "SHORT", 4: "LONG", 5: "RATIONAL",
              6: "SBYTE", 7: "UNDEFINED", 8: "SSHORT", 9: "SLONG",
              10: "SRATIONAL", 11: "FLOAT", 12: "DOUBLE", 13: "IFD"}

COMPRESSION = {
    1: "未压缩 (None)",
    2: "CCITT 改良 Huffman RLE (Group 3 一维)",
    3: "CCITT G3 传真 (T.4)",
    4: "CCITT G4 传真 (T.6)",
    5: "LZW",
    6: "JPEG(旧式, 已废弃)",
    7: "JPEG(新式)",
    8: "Deflate (Adobe)",
    32771: "CCITT RLEW",
    32773: "PackBits",
    32809: "ThunderScan",
    32946: "Deflate (PKZIP 兼容, 旧)",
    34676: "SGI LogL",
    34677: "SGI LogLuv",
    34712: "JPEG 2000",
}
PHOTOMETRIC = {
    0: "WhiteIsZero(0 为白)", 1: "BlackIsZero(0 为黑)", 2: "RGB",
    3: "调色板(Palette)", 4: "透明掩码(Transparency Mask)", 5: "CMYK",
    6: "YCbCr", 8: "CIELab", 9: "ICCLab", 10: "ITULab",
}
RESUNIT = {1: "无单位(1=像素)", 2: "英寸 (inch)", 3: "厘米 (cm)"}

CORE_TAGS = [
    (256, "ImageWidth", "宽度"),
    (257, "ImageLength", "高度"),
    (258, "BitsPerSample", "位深(每样本)"),
    (259, "Compression", "压缩"),
    (262, "PhotometricInterpretation", "光度解释"),
    (277, "SamplesPerPixel", "样本数/像素"),
    (278, "RowsPerStrip", "行数/条带"),
    (273, "StripOffsets", "条带偏移"),
    (279, "StripByteCounts", "条带字节"),
    (282, "XResolution", "X 分辨率"),
    (283, "YResolution", "Y 分辨率"),
    (296, "ResolutionUnit", "分辨率单位"),
]


class TiffError(Exception):
    pass


def setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def die(msg):
    sys.stderr.write("tiff-ifd-summary: 错误: %s\n" % msg)
    raise SystemExit(1)


def read_values(buf, field_off, typ, count, bo):
    """读取标签值: <=4 字节时内联在值字段里(左对齐), 否则为文件偏移。"""
    if typ not in TYPE_SIZES:
        raise TiffError("不支持的标签类型 %d" % typ)
    size = TYPE_SIZES[typ] * count
    if size <= 4:
        raw = buf[field_off:field_off + size]
        if len(raw) < size:
            raise TiffError("内联值被截断")
    else:
        (voff,) = struct.unpack(bo + "I", buf[field_off:field_off + 4])
        if voff + size > len(buf):
            raise TiffError("值数组偏移 0x%X 越界(需要 %d 字节)" % (voff, size))
        raw = buf[voff:voff + size]
    if typ in (3, 8):
        f = "H" if typ == 3 else "h"
        return list(struct.unpack(bo + "%d%s" % (count, f), raw))
    if typ in (4, 9, 13):
        f = {4: "I", 9: "i", 13: "I"}[typ]
        return list(struct.unpack(bo + "%d%s" % (count, f), raw))
    if typ in (1, 6, 7):
        return list(raw)
    if typ == 2:
        return [raw.split(b"\x00", 1)[0].decode("latin-1")]
    if typ in (5, 10):
        f = "I" if typ == 5 else "i"
        vals = struct.unpack(bo + "%d%s" % (count * 2, f), raw)
        return [(vals[2 * i], vals[2 * i + 1]) for i in range(count)]
    if typ in (11, 12):
        f = "f" if typ == 11 else "d"
        return list(struct.unpack(bo + "%d%s" % (count, f), raw))
    raise TiffError("类型 %d 未实现" % typ)


def walk_ifds(buf, bo):
    """沿 next 指针遍历 IFD 链, 返回 (ifd 列表, 警告列表)。"""
    warnings = []
    (first,) = struct.unpack(bo + "I", buf[4:8])
    ifds = []
    off = first
    seen = set()
    while off:
        if off in seen:
            warnings.append("IFD 链出现循环(偏移 0x%X 重复), 提前停止" % off)
            break
        seen.add(off)
        if off + 2 > len(buf):
            raise TiffError("IFD 偏移 0x%X 越界" % off)
        (nent,) = struct.unpack(bo + "H", buf[off:off + 2])
        if off + 2 + 12 * nent + 4 > len(buf):
            raise TiffError("IFD(偏移 0x%X, %d 个条目)超出文件末尾" % (off, nent))
        entries = []
        for k in range(nent):
            eo = off + 2 + 12 * k
            tag, typ = struct.unpack(bo + "HH", buf[eo:eo + 4])
            (cnt,) = struct.unpack(bo + "I", buf[eo + 4:eo + 8])
            try:
                values = read_values(buf, eo + 8, typ, cnt, bo)
                entries.append({"tag": tag, "type": typ, "count": cnt, "values": values})
            except TiffError as exc:
                entries.append({"tag": tag, "type": typ, "count": cnt,
                                "values": None, "error": str(exc)})
        (nxt,) = struct.unpack(bo + "I", buf[off + 2 + 12 * nent:off + 6 + 12 * nent])
        ifds.append({"offset": off, "entry_count": nent, "entries": entries, "next": nxt})
        off = nxt
        if len(ifds) > 256:
            warnings.append("IFD 数量超过 256, 强制停止遍历")
            break
    return ifds, warnings


def render_tag(tag, values):
    if values is None:
        return "(读取失败)"
    v0 = values[0] if values else None
    if tag == 258:
        return ", ".join(map(str, values))
    if tag == 259:
        return "%s — %s" % (v0, COMPRESSION.get(v0, "未知压缩算法"))
    if tag == 262:
        return "%s — %s" % (v0, PHOTOMETRIC.get(v0, "未知光度解释"))
    if tag in (282, 283):
        parts = []
        for num, den in values:
            parts.append("%d/%d" % (num, den) + (" = %g" % (num / den) if den else " (分母为 0)"))
        return ", ".join(parts)
    if tag == 296:
        return "%s — %s" % (v0, RESUNIT.get(v0, "未知单位"))
    if tag in (273, 279):
        s = ", ".join(map(str, values[:4]))
        return s + (" …(共 %d 个)" % len(values) if len(values) > 4 else "")
    return ", ".join(map(str, values))


def render_text(res):
    lines = []
    lines.append("文件    : %s (%d 字节)" % (res["file"], res["file_size"]))
    order_name = "小端 (II, Intel)" if res["byte_order"] == "II" else "大端 (MM, Motorola)"
    lines.append("字节序  : %s — %s" % (res["byte_order"], order_name))
    lines.append("魔数    : %d — 经典 TIFF (BigTIFF 为 43)" % res["magic"])
    lines.append("IFD 链  : 共 %d 个 IFD, 首个位于 0x%08X"
                 % (len(res["ifds"]), res["first_ifd_offset"]))
    shown_tags = {t for t, _, _ in CORE_TAGS}
    for ifd in res["ifds"]:
        lines.append("")
        lines.append("IFD #%d @ 0x%08X — %d 个条目:"
                     % (ifd["index"], ifd["offset"], ifd["entry_count"]))
        tags = ifd["tags"]
        for tag, en, zh in CORE_TAGS:
            if tag in tags:
                lines.append("  %s %s = %s" % (zh, en, render_tag(tag, tags[tag])))
        extra = [e for e in ifd["raw_entries"] if e["tag"] not in shown_tags]
        if extra:
            desc = ", ".join("tag %d (%s)" % (e["tag"], TYPE_NAMES.get(e["type"], e["type"]))
                             for e in extra)
            lines.append("  其他标签: %s" % desc)
        nxt = ifd["next"]
        if nxt:
            lines.append("  下一个 IFD = 0x%08X (→ IFD #%d)" % (nxt, ifd["index"] + 1))
        else:
            lines.append("  下一个 IFD = 0 (链结束)")
    lines.append("")
    if res["warnings"]:
        lines.append("警告 (%d 条):" % len(res["warnings"]))
        for w in res["warnings"]:
            lines.append("  - " + w)
    else:
        lines.append("警告: 无")
    return "\n".join(lines) + "\n"


def main(argv=None):
    setup_stdio()
    ap = argparse.ArgumentParser(
        description="解析 TIFF 字节序与 IFD 链, 输出宽高、位深、压缩算法、分辨率单位等核心标签")
    ap.add_argument("file", help="TIFF 文件路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = ap.parse_args(argv)
    try:
        with open(args.file, "rb") as fh:
            buf = fh.read()
    except OSError as exc:
        die("无法读取文件: %s" % exc)
    if len(buf) < 8:
        die("文件只有 %d 字节, 放不下 TIFF 文件头(8 字节)" % len(buf))
    bo_raw = buf[:2]
    if bo_raw == b"II":
        bo = "<"
    elif bo_raw == b"MM":
        bo = ">"
    else:
        die("字节序标记为 %r, 不是 II 或 MM — 不是 TIFF 文件" % bo_raw.decode("latin-1"))
    order_name = "小端 (II, Intel)" if bo_raw == b"II" else "大端 (MM, Motorola)"
    (magic,) = struct.unpack(bo + "H", buf[2:4])
    if magic == 43:
        die("这是 BigTIFF(魔数 43), 本工具仅支持经典 TIFF(魔数 42)")
    if magic != 42:
        die("魔数为 %d, 不是 42 — 不是 TIFF 文件" % magic)
    try:
        ifds, warnings = walk_ifds(buf, bo)
    except TiffError as exc:
        die(str(exc))
    if not ifds:
        warnings.append("IFD 链为空(首个 IFD 偏移为 0)")

    core_names = {t: en for t, en, _ in CORE_TAGS}
    json_ifds = []
    text_ifds = []
    for idx, ifd in enumerate(ifds):
        tags = {}
        for e in ifd["entries"]:
            if e["values"] is None:
                warnings.append("IFD #%d 的 tag %d 读取失败: %s" % (idx, e["tag"], e["error"]))
            tags.setdefault(e["tag"], e["values"])
        json_ifds.append({"index": idx, "offset": ifd["offset"],
                          "entry_count": ifd["entry_count"], "next": ifd["next"],
                          "summary": {core_names[t]: tags[t] for t in tags if t in core_names},
                          "raw_entries": ifd["entries"]})
        text_ifds.append({"index": idx, "offset": ifd["offset"],
                          "entry_count": ifd["entry_count"], "next": ifd["next"],
                          "tags": tags, "raw_entries": ifd["entries"]})

    (first,) = struct.unpack(bo + "I", buf[4:8])
    res = {"file": args.file, "file_size": len(buf), "byte_order": bo_raw.decode("ascii"),
           "byte_order_name": order_name, "magic": magic, "first_ifd_offset": first,
           "ifd_count": len(ifds), "ifds": json_ifds, "warnings": warnings}
    if args.json:
        sys.stdout.write(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
    else:
        res_text = dict(res)
        res_text["ifds"] = text_ifds
        sys.stdout.write(render_text(res_text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
