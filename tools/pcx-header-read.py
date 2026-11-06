#!/usr/bin/env python3
"""PCX 头读取 —— 解析 PCX（ZSoft PC Paintbrush）128 字节文件头。

输出图像宽高、位平面数与每平面位数、编码方式、DPI、每行字节数，
并给出调色板提示（EGA 16 色 / VGA 256 色 / 24 位真彩 / 黑白等）。

示例命令:
    python pcx-header-read.py IMAGE.pcx              # 人类可读输出
    python pcx-header-read.py --json IMAGE.pcx       # JSON 输出
    python pcx-header-read.py --self-test            # 内置自测（临时目录构造样例输入）

仅依赖 Python 标准库。格式依据 ZSoft《.PCX File Format Technical Reference》。
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

VERSIONS = {0: "2.5（黑白）", 2: "2.8（带头部调色板）", 3: "2.8（无调色板）",
            4: "Paintbrush for Windows", 5: "3.0（支持 24 位/256 色）"}
ENCODINGS = {0: "未压缩", 1: "RLE 压缩"}


def _palette_hint(data: bytes, planes: int, bpp: int) -> dict:
    """按平面数 × 每像素位数给出调色板提示。"""
    if planes == 1 and bpp == 8:
        has_vga = len(data) >= 769 and data[-769] == 0x0C
        return {"kind": "vga-256",
                "desc": "1 平面 × 8 位：VGA 256 色调色板位于文件末尾 769 字节（首字节 0x0C）",
                "vga_palette_found_at_end": has_vga}
    if planes == 3 and bpp == 8:
        return {"kind": "truecolor-24bit",
                "desc": "3 平面 × 8 位 = 24 位真彩 RGB，不使用调色板",
                "vga_palette_found_at_end": False}
    if planes == 4 and bpp == 1:
        return {"kind": "ega-16",
                "desc": "4 平面 × 1 位 = 16 色，调色板在文件头偏移 16-63（EGA RGB）",
                "vga_palette_found_at_end": False}
    if planes == 1 and bpp == 1:
        return {"kind": "mono",
                "desc": "1 平面 × 1 位：黑白两色",
                "vga_palette_found_at_end": False}
    if planes == 1 and bpp == 2:
        return {"kind": "cga-4",
                "desc": "1 平面 × 2 位：CGA 式 4 色",
                "vga_palette_found_at_end": False}
    return {"kind": "unknown",
            "desc": f"{planes} 平面 × {bpp} 位/像素（非常见组合）",
            "vga_palette_found_at_end": False}


def parse_pcx(data: bytes, name: str = "<bytes>") -> dict:
    """解析 PCX 文件头 -> 信息字典；失败抛 ValueError。"""
    if len(data) < 128:
        raise ValueError("文件不足 128 字节，放不下 PCX 头")
    if data[0] != 0x0A:
        raise ValueError(f"制造商字节不是 0x0A（实际 0x{data[0]:02X}），不像 PCX 文件")
    version, encoding, bpp = data[1], data[2], data[3]
    xmin, ymin, xmax, ymax = struct.unpack_from("<4H", data, 4)
    hdpi, vdpi = struct.unpack_from("<2H", data, 12)
    planes = data[65]
    bytes_per_line = struct.unpack_from("<H", data, 66)[0]
    palette_info = struct.unpack_from("<H", data, 68)[0]

    info = {
        "file": name,
        "manufacturer": "0x0A",
        "version": version,
        "version_desc": VERSIONS.get(version, f"未知版本 {version}"),
        "encoding": encoding,
        "encoding_desc": ENCODINGS.get(encoding, f"未知编码 {encoding}"),
        "bits_per_pixel_per_plane": bpp,
        "planes": planes,
        "width": xmax - xmin + 1,
        "height": ymax - ymin + 1,
        "window": [xmin, ymin, xmax, ymax],
        "dpi": [hdpi, vdpi],
        "bytes_per_line": bytes_per_line,
        "palette_info": palette_info,
        "header_ega_palette": True,
        "palette_hint": _palette_hint(data, planes, bpp),
        "warnings": [],
    }
    if planes == 0:
        info["warnings"].append("NPlanes 字段为 0（旧版 PCX 常见），通常按 1 个平面（黑白）理解")
    return info


def render(info: dict) -> str:
    ph = info["palette_hint"]
    lines = [
        f"file: {info['file']}",
        f"version: {info['version']} ({info['version_desc']})",
        f"encoding: {info['encoding']} ({info['encoding_desc']})",
        f"width: {info['width']}",
        f"height: {info['height']}",
        f"window: xmin={info['window'][0]} ymin={info['window'][1]} "
        f"xmax={info['window'][2]} ymax={info['window'][3]}",
        f"planes: {info['planes']}",
        f"bits_per_pixel_per_plane: {info['bits_per_pixel_per_plane']}",
        f"dpi: {info['dpi'][0]} x {info['dpi'][1]}",
        f"bytes_per_line: {info['bytes_per_line']}",
        f"palette_info: {info['palette_info']}",
        f"palette_hint: {ph['desc']}",
        f"vga_palette_found_at_end: {'yes' if ph['vga_palette_found_at_end'] else 'no'}",
        "header_ega_palette: yes（头部偏移 16-63 固定 16 色 EGA 调色板）",
    ]
    lines += [f"warning: {w}" for w in info["warnings"]]
    return "\n".join(lines)


def _make_header(planes: int, bpp: int, w: int, h: int,
                 encoding: int = 1, version: int = 5) -> bytes:
    """构造一个最小但字段自洽的 PCX 头（128 字节）。"""
    b = bytearray(128)
    b[0] = 0x0A
    b[1] = version
    b[2] = encoding
    b[3] = bpp
    struct.pack_into("<4H", b, 4, 0, 0, w - 1, h - 1)
    struct.pack_into("<2H", b, 12, 96, 96)
    b[65] = planes
    bpl = (w * bpp + 7) // 8
    if bpl % 2:
        bpl += 1
    struct.pack_into("<H", b, 66, bpl)
    return bytes(b)


def self_test() -> bool:
    """在临时目录构造样例 PCX，逐项断言解析结果。"""
    tmp = tempfile.mkdtemp(prefix="pcx-selftest-")
    try:
        # 1) 16 色：4 平面 × 1 位
        f1 = os.path.join(tmp, "ega16.pcx")
        with open(f1, "wb") as f:
            f.write(_make_header(4, 1, 32, 16) + b"\x00" * 64)
        with open(f1, "rb") as f:
            i1 = parse_pcx(f.read(), f1)
        assert (i1["width"], i1["height"], i1["planes"],
                i1["bits_per_pixel_per_plane"]) == (32, 16, 4, 1), i1
        assert i1["palette_hint"]["kind"] == "ega-16", i1["palette_hint"]
        print("self-test 1/3 16 色 PCX: 32x16, 4 平面 × 1 位, EGA 头部调色板  OK")

        # 2) 256 色：1 平面 × 8 位 + 末尾 VGA 调色板（769 字节，首字节 0x0C）
        f2 = os.path.join(tmp, "vga256.pcx")
        with open(f2, "wb") as f:
            f.write(_make_header(1, 8, 64, 48) + b"\x00" * 100 + b"\x0c" + bytes(range(256)) * 3)
        with open(f2, "rb") as f:
            i2 = parse_pcx(f.read(), f2)
        assert (i2["width"], i2["height"]) == (64, 48), i2
        assert i2["palette_hint"]["kind"] == "vga-256" \
            and i2["palette_hint"]["vga_palette_found_at_end"] is True, i2["palette_hint"]
        print("self-test 2/3 256 色 PCX: 64x48, 1 平面 × 8 位, 末尾找到 VGA 调色板  OK")

        # 3) 24 位真彩 + 坏制造商字节应报错
        i3 = parse_pcx(_make_header(3, 8, 10, 10) + b"\x00" * 20)
        assert i3["palette_hint"]["kind"] == "truecolor-24bit", i3["palette_hint"]
        try:
            parse_pcx(b"\x0b" + b"\x00" * 127)
        except ValueError:
            pass
        else:
            raise AssertionError("坏制造商字节未被拒绝")
        print("self-test 3/3 24 位真彩识别 + 坏头正确拒绝  OK")
        return True
    except AssertionError as e:
        print(f"SELF-TEST FAILED: {e}", file=sys.stderr)
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="解析 PCX 头：宽高、位平面数、每像素位数与调色板提示")
    ap.add_argument("file", nargs="?", help="PCX 文件路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    ap.add_argument("--self-test", action="store_true", help="构造样例输入运行自测")
    args = ap.parse_args(argv)

    if args.self_test:
        return 0 if self_test() else 1
    if not args.file:
        ap.error("需要提供一个 PCX 文件路径（或用 --self-test）")
    try:
        with open(args.file, "rb") as f:
            info = parse_pcx(f.read(), args.file)
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
