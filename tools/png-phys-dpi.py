#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG DPI 读取器：解析 pHYs 块，输出每米像素数、换算 DPI 及图像的物理厘米尺寸。

pHYs 数据共 9 字节：X 每米像素数(4, 大端) + Y 每米像素数(4, 大端) + 单位(1)。
  单位 1 = 米：DPI = 每米像素数 × 0.0254；物理尺寸 = 像素 ÷ 每米像素数 × 100 厘米
  单位 0 = 未知：pHYs 只表达像素宽高比，无法换算 DPI 与厘米尺寸

用法：
    python png-phys-dpi.py <image.png> [--json]

退出码：
    0 = 正常（没有 pHYs 块时给出提示，也返回 0）
    1 = 存在 pHYs 块但数据无法解析（长度不是 9 字节）
    2 = 文件不存在 / 无法读取 / 不是 PNG

示例：
    python png-phys-dpi.py photo.png
    python png-phys-dpi.py photo.png --json
"""

import argparse
import json
import struct
import sys

PNG_SIG = b"\x89PNG\r\n\x1a\n"
INCH_M = 0.0254


def _setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def is_valid_type(raw):
    return len(raw) == 4 and all(65 <= c <= 90 or 97 <= c <= 122 for c in raw)


def parse_chunks(data):
    """严格解析 chunk 序列，返回 ([(raw_type, cdata, offset)], warnings)。"""
    if len(data) < 8 or data[:8] != PNG_SIG:
        raise ValueError("不是 PNG 文件（8 字节签名不符）")
    chunks = []
    warnings = []
    pos = 8
    seen_iend = False
    while pos < len(data):
        if len(data) - pos < 8:
            raise ValueError("offset %d：剩余数据不足一个块头（文件截断）" % pos)
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        raw_type = data[pos + 4:pos + 8]
        if not is_valid_type(raw_type):
            raise ValueError("offset %d：块类型字节非法" % pos)
        end = pos + 8 + length + 4
        if end > len(data):
            raise ValueError("块 %s 被截断（声明 %d 字节，仅剩 %d）"
                             % (raw_type.decode("latin-1"), length,
                                len(data) - pos - 8))
        chunks.append((raw_type, data[pos + 8:pos + 8 + length], pos))
        pos = end
        if raw_type == b"IEND":
            seen_iend = True
            break
    if not seen_iend:
        warnings.append("未找到 IEND 块")
    elif pos < len(data):
        warnings.append("IEND 之后有 %d 字节多余数据" % (len(data) - pos))
    return chunks, warnings


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(
        description="解析 PNG pHYs 块：每米像素数 / DPI / 物理厘米尺寸")
    ap.add_argument("file", help="PNG 文件路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args(argv)

    try:
        with open(args.file, "rb") as fh:
            data = fh.read()
        chunks, warnings = parse_chunks(data)
    except (OSError, ValueError) as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 2

    width = height = None
    for raw_type, cdata, _off in chunks:
        if raw_type == b"IHDR" and len(cdata) >= 8:
            width, height = struct.unpack(">II", cdata[:8])
            break

    result = {"file": args.file, "width_px": width, "height_px": height,
              "ppu_x": None, "ppu_y": None, "unit": None, "unit_name": None,
              "dpi_x": None, "dpi_y": None,
              "width_cm": None, "height_cm": None, "warnings": list(warnings)}

    phys_list = [cdata for raw_type, cdata, _off in chunks if raw_type == b"pHYs"]
    if len(phys_list) > 1:
        result["warnings"].append(
            "发现 %d 个 pHYs 块（规范只允许 1 个），采用第 1 个" % len(phys_list))

    if not phys_list:
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("文件    : %s" % args.file)
            if width is not None:
                print("IHDR    : %d x %d 像素" % (width, height))
            print("pHYs    : 未找到 —— 该 PNG 未声明物理分辨率，"
                  "无法计算 DPI/厘米尺寸")
        return 0

    raw = phys_list[0]
    if len(raw) != 9:
        result["warnings"].append(
            "pHYs 数据长 %d（规范应为 9 字节），无法解析" % len(raw))
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            for w in result["warnings"]:
                print("警告：%s" % w, file=sys.stderr)
        return 1

    ppu_x, ppu_y, unit = struct.unpack(">IIB", raw)
    result["ppu_x"], result["ppu_y"], result["unit"] = ppu_x, ppu_y, unit
    result["unit_name"] = {1: "meter", 0: "unknown"}.get(unit,
                                                         "nonstandard(%d)" % unit)
    if unit == 1:
        result["dpi_x"] = round(ppu_x * INCH_M, 2)
        result["dpi_y"] = round(ppu_y * INCH_M, 2)
        if width is not None and ppu_x:
            result["width_cm"] = round(width / ppu_x * 100, 2)
        if height is not None and ppu_y:
            result["height_cm"] = round(height / ppu_y * 100, 2)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print("文件    : %s" % args.file)
    if width is not None:
        print("IHDR    : %d x %d 像素" % (width, height))
    if unit == 1:
        print("pHYs    : X = %d px/m，Y = %d px/m，单位 = 米(1)" % (ppu_x, ppu_y))
        print("DPI     : X = %.2f，Y = %.2f（1 英寸 = 0.0254 米）"
              % (ppu_x * INCH_M, ppu_y * INCH_M))
        if width is not None:
            print("物理尺寸 : %d x %d 像素 = %.2f cm x %.2f cm"
                  % (width, height, result["width_cm"], result["height_cm"]))
    else:
        print("pHYs    : X = %d px/m，Y = %d px/m，单位 = %s"
              % (ppu_x, ppu_y, result["unit_name"]))
        print("DPI     : 无法换算（单位未知/非标准，pHYs 仅表示像素宽高比）")
    for w in result["warnings"]:
        print("警告：%s" % w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
