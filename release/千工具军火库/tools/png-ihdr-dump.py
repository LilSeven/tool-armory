#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG IHDR 转储 —— 解析 PNG 头部的 IHDR 块, 输出并解释全部 7 个字段。

按 PNG 规范校验 8 字节签名与第一个数据块(必须为 IHDR), 校验块 CRC,
然后输出图像宽、高、位深、颜色类型、压缩方法、滤波方法、隔行方式,
并逐一解释各字段含义; 对不符合规范的字段组合给出警告。

用法:
    python png-ihdr-dump.py <文件.png> [--json]

示例:
    python png-ihdr-dump.py sample.png
    python png-ihdr-dump.py sample.png --json

退出码: 0 = 解析成功; 1 = 文件不存在 / 不是 PNG / IHDR 损坏。
仅使用 Python 标准库, 需 Python 3.7+。
"""

import argparse
import json
import struct
import sys
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"

# 颜色类型: 值 -> (名称, 每像素通道数, 允许的位深)
COLOR_TYPES = {
    0: ("灰度 grayscale", 1, (1, 2, 4, 8, 16)),
    2: ("真彩色 truecolor RGB", 3, (8, 16)),
    3: ("索引色 indexed(调色板)", 1, (1, 2, 4, 8)),
    4: ("灰度+Alpha grayscale+alpha", 2, (8, 16)),
    6: ("真彩色+Alpha truecolor+alpha", 4, (8, 16)),
}
INTERLACE = {
    0: "不隔行: 逐行顺序扫描",
    1: "Adam7 七遍隔行: 图像分 7 遍交错传输",
}
FILTER_MEANING = "自适应滤波: 每行行首 1 字节从 None/Sub/Up/Average/Paeth 中选择"


class ToolError(Exception):
    pass


def setup_stdio():
    """Windows 控制台/管道下强制 UTF-8 输出, 避免中文乱码或崩溃。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def die(msg):
    sys.stderr.write("png-ihdr-dump: 错误: %s\n" % msg)
    raise SystemExit(1)


def parse(path):
    try:
        with open(path, "rb") as fh:
            blob = fh.read()
    except OSError as exc:
        raise ToolError("无法读取文件: %s" % exc)
    if len(blob) < 8:
        raise ToolError("文件只有 %d 字节, 连 PNG 签名(8 字节)都放不下" % len(blob))
    if blob[:8] != SIGNATURE:
        raise ToolError("PNG 签名不匹配: 前 8 字节为 %s" % blob[:8].hex(" "))
    if len(blob) < 16:
        raise ToolError("文件在块长度字段处截断, 没有 IHDR")
    (length,) = struct.unpack(">I", blob[8:12])
    ctype = blob[12:16]
    if ctype != b"IHDR":
        raise ToolError("第一个块类型为 %r, 不是 IHDR" % ctype.decode("latin-1"))
    if length != 13:
        raise ToolError("IHDR 数据长度应为 13 字节, 实际为 %d" % length)
    data = blob[16:16 + length]
    if len(data) != length or len(blob) < 20 + length:
        raise ToolError("IHDR 块不完整(应为 13 字节数据 + 4 字节 CRC)")
    (stored_crc,) = struct.unpack(">I", blob[16 + length:20 + length])
    calc_crc = zlib.crc32(ctype + data) & 0xFFFFFFFF

    width, height = struct.unpack(">II", data[0:8])
    bit_depth, color_type, compression, filt, interlace = data[8:13]

    warnings = []
    color_name, channels, allowed = COLOR_TYPES.get(color_type, (None, None, ()))
    if color_name is None:
        warnings.append("颜色类型 %d 非法(PNG 仅定义 0/2/3/4/6)" % color_type)
    elif bit_depth not in allowed:
        warnings.append("位深 %d 与颜色类型 %d 是不允许的组合(允许: %s)"
                        % (bit_depth, color_type, "/".join(map(str, allowed))))
    if compression != 0:
        warnings.append("压缩方法 %d 非法, PNG 仅定义 0(Deflate)" % compression)
    if filt != 0:
        warnings.append("滤波方法 %d 非法, PNG 仅定义 0(自适应滤波)" % filt)
    if interlace not in INTERLACE:
        warnings.append("隔行方式 %d 非法, 仅允许 0 或 1" % interlace)

    return {
        "file": path,
        "file_size": len(blob),
        "signature_ok": True,
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "color_type": color_type,
        "color_type_name": color_name,
        "channels": channels,
        "compression": compression,
        "filter": filt,
        "interlace": interlace,
        "crc_stored": "0x%08X" % stored_crc,
        "crc_calculated": "0x%08X" % calc_crc,
        "crc_ok": stored_crc == calc_crc,
        "warnings": warnings,
    }


def render_text(res):
    lines = []
    lines.append("文件       : %s (%d 字节)" % (res["file"], res["file_size"]))
    lines.append("PNG 签名   : OK (89 50 4E 47 0D 0A 1A 0A)")
    crc = "校验通过" if res["crc_ok"] else "不匹配!"
    lines.append("IHDR 块    : 数据 13 字节, CRC %s (存储 %s / 计算 %s)"
                 % (crc, res["crc_stored"], res["crc_calculated"]))
    lines.append("")
    lines.append("字段解析 (IHDR 的 7 个字段, 数据部分共 13 字节):")
    lines.append("  width  宽度         = %d 像素 (4 字节无符号大端整数)" % res["width"])
    lines.append("  height 高度         = %d 像素" % res["height"])
    lines.append("  bit_depth 位深      = %d — 每采样(每通道)位数" % res["bit_depth"])
    if res["color_type_name"]:
        lines.append("  color_type 颜色类型 = %d — %s; 每像素 %d 通道"
                     % (res["color_type"], res["color_type_name"], res["channels"]))
    else:
        lines.append("  color_type 颜色类型 = %d — 非法值" % res["color_type"])
    lines.append("  compression 压缩方法 = %d — Deflate/inflate (zlib 压缩, PNG 仅定义方法 0)"
                 % res["compression"])
    lines.append("  filter 滤波方法     = %d — %s" % (res["filter"], FILTER_MEANING))
    lines.append("  interlace 隔行方式  = %d — %s"
                 % (res["interlace"], INTERLACE.get(res["interlace"], "非法值")))
    lines.append("")
    if res["warnings"]:
        lines.append("警告 (%d 条):" % len(res["warnings"]))
        for w in res["warnings"]:
            lines.append("  - " + w)
    else:
        lines.append("警告: 无 — 各字段取值均符合 PNG 规范 (ISO/IEC 15948)")
    return "\n".join(lines) + "\n"


def main(argv=None):
    setup_stdio()
    ap = argparse.ArgumentParser(
        description="解析 PNG 文件的 IHDR 块, 输出并解释宽高、位深、颜色类型、压缩/滤波/隔行方式")
    ap.add_argument("file", help="PNG 文件路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = ap.parse_args(argv)
    try:
        res = parse(args.file)
    except ToolError as exc:
        die(str(exc))
    if args.json:
        sys.stdout.write(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(render_text(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
