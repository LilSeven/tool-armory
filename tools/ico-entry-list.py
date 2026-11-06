#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ICO 条目列表 —— 解析 ICO/CUR 文件目录, 列出每个内嵌图标的宽高、颜色数与字节偏移。

读取 6 字节 ICONDIR(reserved/type/count)与每条 16 字节的 ICONDIRENTRY,
输出每个内嵌图像的宽、高、颜色数、位深、数据字节数与文件偏移,
并探测内嵌数据的格式(PNG 签名或 BMP 信息头)。CUR 文件的
planes/bitCount 字段按规范实为热点(hotspot)坐标。

用法:
    python ico-entry-list.py <文件.ico|文件.cur> [--json]

示例:
    python ico-entry-list.py favicon.ico
    python ico-entry-list.exe favicon.ico --json

退出码: 0 = 解析成功; 1 = 不是 ICO/CUR 或目录损坏。
仅使用 Python 标准库, 需 Python 3.7+。
"""

import argparse
import json
import struct
import sys

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
BMP_INFO_HEADER_SIZES = (40, 52, 56, 64, 108, 124)  # BITMAPINFOHEADER 及 V4/V5 扩展


class ToolError(Exception):
    pass


def setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def die(msg):
    sys.stderr.write("ico-entry-list: 错误: %s\n" % msg)
    raise SystemExit(1)


def parse(path):
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise ToolError("无法读取文件: %s" % exc)
    if len(data) < 6:
        raise ToolError("文件只有 %d 字节, 放不下 ICONDIR(6 字节)" % len(data))
    reserved, rtype, count = struct.unpack("<HHH", data[:6])
    if rtype not in (1, 2):
        raise ToolError("类型字段 = %d, 不是 1(ICO) 也不是 2(CUR) — 不是 ICO/CUR 文件" % rtype)
    warnings = []
    if reserved != 0:
        warnings.append("保留字段应为 0, 实际为 %d" % reserved)
    if 6 + 16 * count > len(data):
        raise ToolError("目录声明 %d 个条目(需要 %d 字节), 文件只有 %d 字节, 目录被截断"
                        % (count, 6 + 16 * count, len(data)))
    if count == 0:
        warnings.append("目录项数为 0 — 文件中没有内嵌图像")

    entries = []
    for i in range(count):
        eo = 6 + i * 16
        w, h, ncol, resv, planes, bits, size, off = struct.unpack(
            "<BBBBHHII", data[eo:eo + 16])
        if resv != 0:
            warnings.append("条目 %d 的保留字节应为 0, 实际为 %d" % (i, resv))
        blob = data[off:off + size]
        fmt = "未知"
        if len(blob) < size:
            warnings.append("条目 %d 数据被截断: 声明 %d 字节 @0x%X, 文件仅剩 %d 字节"
                            % (i, size, off, len(blob)))
            fmt = "(截断)"
        elif blob[:8] == PNG_SIGNATURE:
            fmt = "PNG"
        elif len(blob) >= 4 and struct.unpack("<I", blob[:4])[0] in BMP_INFO_HEADER_SIZES:
            fmt = "BMP"
        note = ""
        if rtype == 2:
            note = "热点 X=%d, Y=%d" % (planes, bits)
        entries.append({
            "index": i,
            "width": 256 if w == 0 else w,
            "height": 256 if h == 0 else h,
            "raw_width_byte": w,
            "raw_height_byte": h,
            "colors": ncol,
            "planes": planes,
            "bit_count": bits,
            "bytes": size,
            "offset": off,
            "offset_hex": "0x%08X" % off,
            "format": fmt,
            "note": note,
        })
    return {
        "file": path,
        "file_size": len(data),
        "type": rtype,
        "kind": "图标 (ICO)" if rtype == 1 else "光标 (CUR)",
        "count": count,
        "entries": entries,
        "warnings": warnings,
    }


def render_text(res):
    lines = []
    lines.append("文件: %s (%d 字节)" % (res["file"], res["file_size"]))
    lines.append("类型: %s (type=%d), 目录项数: %d" % (res["kind"], res["type"], res["count"]))
    lines.append("说明: 宽高字节 0 表示 256; 颜色数 0 表示无调色板(>=256 色或内嵌 PNG)")
    if res["type"] == 2:
        lines.append("      CUR 的 planes/bitCount 字段按规范存放热点坐标")
    lines.append("")
    lines.append(" #   宽×高      颜色数  位深  数据字节  偏移        格式")
    for e in res["entries"]:
        fmt = e["format"] + ("; " + e["note"] if e["note"] else "")
        lines.append(" %-3d %-10s %-7d %-5d %-9d %s  %s"
                     % (e["index"] + 1, "%d×%d" % (e["width"], e["height"]),
                        e["colors"], e["bit_count"], e["bytes"], e["offset_hex"], fmt))
    lines.append("")
    if res["warnings"]:
        lines.append("警告 (%d 条):" % len(res["warnings"]))
        for w in res["warnings"]:
            lines.append("  - " + w)
    else:
        lines.append("警告: 无 — 所有条目的数据范围均在文件之内")
    return "\n".join(lines) + "\n"


def main(argv=None):
    setup_stdio()
    ap = argparse.ArgumentParser(
        description="解析 ICO/CUR 目录, 列出每个内嵌图标的宽高、颜色数与字节偏移")
    ap.add_argument("file", help="ICO 或 CUR 文件路径")
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
