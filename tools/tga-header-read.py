#!/usr/bin/env python3
"""TGA 头读取 —— 解析 Truevision TGA（TARGA）18 字节文件头。

输出宽高、像素位深、图像类型（颜色映射/真彩/灰度 × 未压缩/RLE）、
像素数据原点方位与像素深度描述（含 alpha 位数）。

示例命令:
    python tga-header-read.py IMAGE.tga              # 人类可读输出
    python tga-header-read.py --json IMAGE.tga       # JSON 输出
    python tga-header-read.py --self-test            # 内置自测（临时目录构造样例输入）

仅依赖 Python 标准库。格式依据 Truevision《TGA File Format Specification 2.0》。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import sys
import tempfile

# Windows 控制台编码兜底
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

IMAGE_TYPES = {
    0: "无图像数据", 1: "未压缩 颜色映射", 2: "未压缩 真彩", 3: "未压缩 灰度",
    9: "RLE 颜色映射", 10: "RLE 真彩", 11: "RLE 灰度",
    32: "Huffman/Delta+RLE（罕见）", 33: "Huffman/Delta+RLE 多块（罕见）",
}
CMAP_TYPES = {0: "无颜色映射", 1: "有颜色映射"}
TGA_FOOTER = b"TRUEVISION-XFILE.\x00"
_KIND = {0: "none", 1: "colormapped", 9: "colormapped", 2: "truecolor",
         10: "truecolor", 3: "grayscale", 11: "grayscale"}


def parse_tga(data: bytes, name: str = "<bytes>") -> dict:
    """解析 TGA 文件头 -> 信息字典；失败抛 ValueError。"""
    if len(data) < 18:
        raise ValueError("文件不足 18 字节，放不下 TGA 头")
    id_len, cmap_type, image_type = data[0], data[1], data[2]
    cmap_first, cmap_len = struct.unpack_from("<2H", data, 3)
    cmap_entry_size = data[7]  # 偏移 3-4=首项索引, 5-6=映射长度, 7=每项位数
    x_origin, y_origin = struct.unpack_from("<2H", data, 8)
    width, height = struct.unpack_from("<2H", data, 12)
    pixel_depth = data[16]
    descriptor = data[17]

    alpha_bits = descriptor & 0x0F
    right_origin = bool(descriptor & 0x10)
    top_origin = bool(descriptor & 0x20)
    interleave = (descriptor >> 6) & 0x03

    warnings = []
    if image_type not in IMAGE_TYPES:
        warnings.append(f"图像类型 {image_type} 不是规范值")
    if image_type in (1, 9) and cmap_type != 1:
        warnings.append("颜色映射类图像但颜色映射类型不是 1")
    if image_type in (2, 3, 10, 11) and cmap_type != 0:
        warnings.append("真彩/灰度图像却带颜色映射（规范要求类型 0）")
    if pixel_depth not in (8, 15, 16, 24, 32):
        warnings.append(f"像素位深 {pixel_depth} 不是常见值（8/15/16/24/32）")
    if interleave:
        warnings.append(f"描述符保留/交错位非 0（={interleave}），TGA 2.0 要求为 0")

    kind = _KIND.get(image_type, "unknown")
    if kind == "colormapped":
        depth_desc = f"{pixel_depth} 位调色板索引 × {cmap_entry_size} 位/项，映射表 {cmap_len} 项"
    elif kind == "truecolor":
        depth_desc = f"{pixel_depth} 位/像素真彩（BGR 顺序），alpha {alpha_bits} 位"
    elif kind == "grayscale":
        depth_desc = f"{pixel_depth} 位/像素灰度，alpha {alpha_bits} 位"
    else:
        depth_desc = f"{pixel_depth} 位/像素（类型未知）"

    origin = ("top" if top_origin else "bottom") + "-" + ("right" if right_origin else "left")

    return {
        "file": name,
        "id_length": id_len,
        "image_id": data[18:18 + id_len].decode("ascii", "replace") if id_len else "",
        "color_map_type": cmap_type,
        "color_map_type_desc": CMAP_TYPES.get(cmap_type, f"未知类型 {cmap_type}"),
        "image_type": image_type,
        "image_type_desc": IMAGE_TYPES.get(image_type, f"未知类型 {image_type}"),
        "color_map": {"first_entry": cmap_first, "length": cmap_len,
                      "entry_size": cmap_entry_size},
        "width": width,
        "height": height,
        "x_origin": x_origin,
        "y_origin": y_origin,
        "pixel_depth": pixel_depth,
        "alpha_bits": alpha_bits,
        "origin": origin,
        "origin_note": "第一像素在屏幕上的方位（描述符 bit5=上下, bit4=左右）",
        "pixel_depth_desc": depth_desc,
        "has_tga2_footer": len(data) >= 18 and data[-18:] == TGA_FOOTER,
        "warnings": warnings,
    }


def render(info: dict) -> str:
    cm = info["color_map"]
    lines = [
        f"file: {info['file']}",
        f"width: {info['width']}",
        f"height: {info['height']}",
        f"pixel_depth: {info['pixel_depth']} bits",
        f"image_type: {info['image_type']} ({info['image_type_desc']})",
        f"color_map_type: {info['color_map_type']} ({info['color_map_type_desc']})",
        f"color_map: first={cm['first_entry']} length={cm['length']} entry_size={cm['entry_size']}",
        f"origin: {info['origin']}（{info['origin_note']}）",
        f"alpha_bits: {info['alpha_bits']}",
        f"pixel_depth_desc: {info['pixel_depth_desc']}",
        f"tga2_footer: {'yes' if info['has_tga2_footer'] else 'no'}",
    ]
    if info["id_length"]:
        lines.append(f"image_id: {info['image_id']!r}")
    lines += [f"warning: {w}" for w in info["warnings"]]
    return "\n".join(lines)


def _make_tga(image_type: int, width: int, height: int, depth: int, descriptor: int,
              cmap_type: int = 0, cmap_first: int = 0, cmap_len: int = 0,
              cmap_entry_size: int = 0, image_id: bytes = b"",
              body: bytes = b"") -> bytes:
    """构造一个最小 TGA 文件（头 + 图像 ID + 数据体）。"""
    header = struct.pack("<BBB", len(image_id), cmap_type, image_type)
    header += struct.pack("<HHB", cmap_first, cmap_len, cmap_entry_size)
    header += struct.pack("<HHHH", 0, 0, width, height)
    header += struct.pack("<BB", depth, descriptor)
    return header + image_id + body


def self_test() -> bool:
    """在临时目录构造样例 TGA，逐项断言解析结果。"""
    tmp = tempfile.mkdtemp(prefix="tga-selftest-")
    try:
        # 1) 未压缩 32 位 RGBA，原点左上，带 TGA 2.0 结尾
        f1 = os.path.join(tmp, "rgba.tga")
        with open(f1, "wb") as f:
            f.write(_make_tga(2, 16, 16, 32, 0x28, body=b"\x00" * (16 * 16 * 4)) + TGA_FOOTER)
        with open(f1, "rb") as f:
            i1 = parse_tga(f.read(), f1)
        assert (i1["width"], i1["height"], i1["pixel_depth"], i1["image_type"]) \
            == (16, 16, 32, 2), i1
        assert i1["origin"] == "top-left" and i1["alpha_bits"] == 8, i1
        assert i1["has_tga2_footer"] is True and not i1["warnings"], i1
        print("self-test 1/3 真彩 TGA: 16x16, 32 位 + 8 位 alpha, 原点 top-left, TGA2 结尾  OK")

        # 2) RLE 灰度，原点左下（经典 TGA 方向）
        f2 = os.path.join(tmp, "gray.tga")
        with open(f2, "wb") as f:
            f.write(_make_tga(11, 8, 8, 8, 0x00, body=b"\x00" * 16))
        with open(f2, "rb") as f:
            i2 = parse_tga(f.read(), f2)
        assert (i2["image_type"], i2["image_type_desc"], i2["origin"]) \
            == (11, "RLE 灰度", "bottom-left"), i2
        assert i2["pixel_depth_desc"] == "8 位/像素灰度，alpha 0 位", i2
        print("self-test 2/3 RLE 灰度 TGA: 8x8, 8 位, 原点 bottom-left  OK")

        # 3) 颜色映射图 + 超短文件应报错
        i3 = parse_tga(_make_tga(1, 4, 4, 8, 0x20, cmap_type=1, cmap_len=2, cmap_entry_size=24))
        assert i3["pixel_depth_desc"] == "8 位调色板索引 × 24 位/项，映射表 2 项", i3
        assert i3["color_map_type_desc"] == "有颜色映射", i3
        try:
            parse_tga(b"\x00" * 10)
        except ValueError:
            pass
        else:
            raise AssertionError("超短文件未被拒绝")
        print("self-test 3/3 颜色映射识别 + 超短文件正确拒绝  OK")
        return True
    except AssertionError as e:
        print(f"SELF-TEST FAILED: {e}", file=sys.stderr)
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="解析 TGA 头：宽高、位深、图像类型、原点与像素深度描述")
    ap.add_argument("file", nargs="?", help="TGA 文件路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    ap.add_argument("--self-test", action="store_true", help="构造样例输入运行自测")
    args = ap.parse_args(argv)

    if args.self_test:
        return 0 if self_test() else 1
    if not args.file:
        ap.error("需要提供一个 TGA 文件路径（或用 --self-test）")
    try:
        with open(args.file, "rb") as f:
            info = parse_tga(f.read(), args.file)
    except OSError as e:
        print(f"error: 无法读取文件: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(info, ensure_ascii=False, indent=2) if args.json else render(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
