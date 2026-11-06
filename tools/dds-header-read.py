#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DDS 头读取器(dds-header-read) —— 解析 .dds 文件头，输出宽高、mipmap 层数与像素格式。

用途:
    读取 DirectDraw Surface 文件的 124 字节 DDS_HEADER(以及 fourcc 为 'DX10'
    时的 20 字节 DDS_HEADER_DXT10 扩展头)，输出图像宽/高、mipmap 层数与像素
    格式：压缩格式打印四字符码(fourcc，如 DXT1/BC7S)；DX10 扩展头打印 DXGI
    格式名、资源维度与数组大小；未压缩格式按位计数与 RGBA 掩码推导名称
    (如 A8R8G8B8/R5G6B5)。

用法:
    python dds-header-read.py <file.dds> [--json]
    python dds-header-read.py --make-sample <out.dds>    生成一张示例 DXT1 贴图
    python dds-header-read.py --selftest                 构造示例输入并自校验

示例:
    python dds-header-read.py texture.dds
    python dds-header-read.py texture.dds --json
    python dds-header-read.py --make-sample demo.dds
    python dds-header-read.py --selftest

退出码: 0=成功; 1=文件不是 DDS 或头损坏; 2=命令行用法错误。
仅使用 Python 标准库(argparse/json/struct/tempfile/os)。
"""

import argparse
import json
import os
import struct
import sys
import tempfile

MAGIC = b"DDS "
HEADER_SIZE = 124
DX10_SIZE = 20
DX10_FOURCC = 0x30315844  # 'DX10' 按小端打包成的整数

DDSD_FLAGS = {
    0x00000001: "DDSD_CAPS",
    0x00000002: "DDSD_HEIGHT",
    0x00000004: "DDSD_WIDTH",
    0x00000008: "DDSD_PITCH",
    0x00001000: "DDSD_PIXELFORMAT",
    0x00020000: "DDSD_MIPMAPCOUNT",
    0x00080000: "DDSD_LINEARSIZE",
    0x00800000: "DDSD_DEPTH",
}

DDPF_FLAGS = {
    0x00000001: "DDPF_ALPHAPIXELS",
    0x00000002: "DDPF_ALPHA",
    0x00000004: "DDPF_FOURCC",
    0x00000040: "DDPF_RGB",
    0x00000200: "DDPF_YUV",
    0x00020000: "DDPF_LUMINANCE",
}

DDSCAPS_FLAGS = {0x8: "COMPLEX", 0x1000: "TEXTURE", 0x400000: "MIPMAP"}
DDSCAPS2_FLAGS = {
    0x200: "CUBEMAP", 0x400: "CUBEMAP_POSITIVEX", 0x800: "CUBEMAP_NEGATIVEX",
    0x1000: "CUBEMAP_POSITIVEY", 0x2000: "CUBEMAP_NEGATIVEY",
    0x4000: "CUBEMAP_POSITIVEZ", 0x8000: "CUBEMAP_NEGATIVEZ", 0x200000: "VOLUME",
}

DXGI_FORMAT_NAMES = {
    0: "UNKNOWN", 1: "R32G32B32A32_TYPELESS", 2: "R32G32B32A32_FLOAT",
    3: "R32G32B32A32_UINT", 4: "R32G32B32A32_SINT", 5: "R32G32B32_TYPELESS",
    6: "R32G32B32_FLOAT", 7: "R32G32B32_UINT", 8: "R32G32B32_SINT",
    9: "R16G16B16A16_TYPELESS", 10: "R16G16B16A16_FLOAT", 11: "R16G16B16A16_UNORM",
    12: "R16G16B16A16_UINT", 13: "R16G16B16A16_SNORM", 14: "R16G16B16A16_SINT",
    15: "R32G32_TYPELESS", 16: "R32G32_FLOAT", 17: "R32G32_UINT", 18: "R32G32_SINT",
    19: "R32G8X24_TYPELESS", 20: "D32_FLOAT_S8X24_UINT",
    21: "R32_FLOAT_X8X24_TYPELESS", 22: "X32_TYPELESS_G8X24_UINT",
    23: "R10G10B10A2_TYPELESS", 24: "R10G10B10A2_UNORM", 25: "R10G10B10A2_UINT",
    26: "R11G11B10_FLOAT", 27: "R8G8B8A8_TYPELESS", 28: "R8G8B8A8_UNORM",
    29: "R8G8B8A8_UNORM_SRGB", 30: "R8G8B8A8_UINT", 31: "R8G8B8A8_SNORM",
    32: "R8G8B8A8_SINT", 33: "R16G16_TYPELESS", 34: "R16G16_FLOAT",
    35: "R16G16_UNORM", 36: "R16G16_UINT", 37: "R16G16_SNORM", 38: "R16G16_SINT",
    39: "R32_TYPELESS", 40: "D32_FLOAT", 41: "R32_FLOAT", 42: "R32_UINT",
    43: "R32_SINT", 44: "R24G8_TYPELESS", 45: "D24_UNORM_S8_UINT",
    46: "R24_UNORM_X8_TYPELESS", 47: "X24_TYPELESS_G8_UINT", 48: "R8G8_TYPELESS",
    49: "R8G8_UNORM", 50: "R8G8_UINT", 51: "R8G8_SNORM", 52: "R8G8_SINT",
    53: "R16_TYPELESS", 54: "R16_FLOAT", 55: "D16_UNORM", 56: "R16_UNORM",
    57: "R16_UINT", 58: "R16_SNORM", 59: "R16_SINT", 60: "R8_TYPELESS",
    61: "R8_UNORM", 62: "R8_UINT", 63: "R8_SNORM", 64: "R8_SINT", 65: "A8_UNORM",
    66: "R1_UNORM", 67: "R9G9B9E5_SHAREDEXP", 68: "R8G8_B8G8_UNORM",
    69: "G8R8_G8B8_UNORM", 70: "BC1_TYPELESS", 71: "BC1_UNORM",
    72: "BC1_UNORM_SRGB", 73: "BC2_TYPELESS", 74: "BC2_UNORM",
    75: "BC2_UNORM_SRGB", 76: "BC3_TYPELESS", 77: "BC3_UNORM",
    78: "BC3_UNORM_SRGB", 79: "BC4_TYPELESS", 80: "BC4_UNORM", 81: "BC4_SNORM",
    82: "BC5_TYPELESS", 83: "BC5_UNORM", 84: "BC5_SNORM", 85: "B5G6R5_UNORM",
    86: "B5G5R5A1_UNORM", 87: "B8G8R8A8_UNORM", 88: "B8G8R8X8_UNORM",
    89: "R10G10B10_XR_BIAS_A2_UNORM", 90: "B8G8R8A8_TYPELESS",
    91: "B8G8R8A8_UNORM_SRGB", 92: "B8G8R8X8_TYPELESS",
    93: "B8G8R8X8_UNORM_SRGB", 94: "BC6H_TYPELESS", 95: "BC6H_UF16",
    96: "BC6H_SF16", 97: "BC7_TYPELESS", 98: "BC7_UNORM", 99: "BC7_UNORM_SRGB",
}

RESOURCE_DIMENSIONS = {0: "UNKNOWN", 1: "BUFFER", 2: "TEXTURE1D", 3: "TEXTURE2D", 4: "TEXTURE3D"}
ALPHA_MODES = {0: "UNKNOWN", 1: "STRAIGHT", 2: "PREMULTIPLIED", 3: "OPAQUE", 4: "CUSTOM"}

# (位计数, R 掩码, G 掩码, B 掩码, A 掩码, 名称)
UNCOMPRESSED_TABLE = [
    (32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000, "A8R8G8B8"),
    (32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0x00000000, "R8G8B8 (32bpp, alpha mask 0)"),
    (24, 0x00FF0000, 0x0000FF00, 0x000000FF, 0x00000000, "R8G8B8"),
    (16, 0x0000F800, 0x000007E0, 0x0000001F, 0x00000000, "R5G6B5"),
    (16, 0x00007C00, 0x000003E0, 0x0000001F, 0x00008000, "A1R5G5B5"),
    (16, 0x00000F00, 0x000000F0, 0x0000000F, 0x0000F000, "A4R4G4B4"),
    (8, 0x000000FF, 0x00000000, 0x00000000, 0x00000000, "8bpp (luminance-style)"),
]


class DDSError(ValueError):
    """DDS 解析失败。"""


def flags_to_names(table, value):
    names = [n for bit, n in sorted(table.items()) if value & bit]
    known = 0
    for bit in table:
        if value & bit:
            known |= bit
    rest = value & ~known
    if rest:
        names.append("unknown=0x%08X" % rest)
    return "|".join(names) if names else "0"


def fourcc_text(value):
    raw = int(value).to_bytes(4, "little")
    if all(0x20 <= c <= 0x7E for c in raw):
        return raw.decode("ascii")
    return "0x%08X" % value


def parse_dds(data):
    """解析 DDS 头，返回结果 dict；非法输入抛 DDSError。"""
    if data[:4] != MAGIC:
        raise DDSError("not a DDS file (magic=%r, want %r)" % (bytes(data[:4]), MAGIC))
    if len(data) < 4 + HEADER_SIZE:
        raise DDSError("too short for a DDS header: %d bytes" % len(data))
    hdr = data[4:4 + HEADER_SIZE]
    (dw_size, dw_flags, height, width,
     pitch_linear, depth, mipmap_count) = struct.unpack_from("<7I", hdr, 0)
    if dw_size != HEADER_SIZE:
        raise DDSError("header dwSize=%d, expected %d" % (dw_size, HEADER_SIZE))
    pf_size, pf_flags, fourcc, rgb_bits, r_mask, g_mask, b_mask, a_mask = \
        struct.unpack_from("<8I", hdr, 72)
    if pf_size != 32:
        raise DDSError("DDS_PIXELFORMAT dwSize=%d, expected 32" % pf_size)
    caps, caps2, _caps3, _caps4, _res2 = struct.unpack_from("<5I", hdr, 104)

    dx10 = None
    if fourcc == DX10_FOURCC:
        if len(data) < 4 + HEADER_SIZE + DX10_SIZE:
            raise DDSError("fourcc is 'DX10' but the 20-byte extension header is missing")
        dxgi_format, resource_dim, misc_flag, array_size, misc2 = \
            struct.unpack_from("<5I", data, 4 + HEADER_SIZE)
        dx10 = {
            "dxgi_format": DXGI_FORMAT_NAMES.get(dxgi_format, "0x%X" % dxgi_format),
            "dxgi_format_id": dxgi_format,
            "resource_dimension": RESOURCE_DIMENSIONS.get(resource_dim, str(resource_dim)),
            "misc_flag": misc_flag,
            "array_size": array_size,
            "alpha_mode": ALPHA_MODES.get(misc2, str(misc2)),
        }

    mipmaps = mipmap_count if (dw_flags & 0x00020000) and mipmap_count else 1

    if dx10 is not None:
        pixel_format = "DX10/%s" % dx10["dxgi_format"]
    elif (pf_flags & 0x4) and fourcc:
        pixel_format = fourcc_text(fourcc)
    else:
        pixel_format = None
        for bits, r, g, b, a, name in UNCOMPRESSED_TABLE:
            if rgb_bits == bits and (r_mask, g_mask, b_mask, a_mask) == (r, g, b, a):
                pixel_format = name
                break
        if pixel_format is None:
            pixel_format = "uncompressed %d-bit (R=0x%08X G=0x%08X B=0x%08X A=0x%08X)" % (
                rgb_bits, r_mask, g_mask, b_mask, a_mask)

    return {
        "file_size": len(data),
        "width": width,
        "height": height,
        "mipmaps": mipmaps,
        "depth": depth if (dw_flags & 0x00800000) and depth else None,
        "fourcc": fourcc_text(fourcc) if fourcc else None,
        "pixel_format": pixel_format,
        "header_flags": flags_to_names(DDSD_FLAGS, dw_flags),
        "pf_flags": flags_to_names(DDPF_FLAGS, pf_flags),
        "rgb_bit_count": rgb_bits,
        "masks": {"r": r_mask, "g": g_mask, "b": b_mask, "a": a_mask},
        "pitch_or_linear_size": pitch_linear,
        "caps": flags_to_names(DDSCAPS_FLAGS, caps),
        "caps2": flags_to_names(DDSCAPS2_FLAGS, caps2),
        "cubemap": bool(caps2 & 0x200),
        "volume": bool(caps2 & 0x200000),
        "dx10": dx10,
    }


def format_text(info):
    lines = [
        "file:            %s" % info.get("path", "<memory>"),
        "size:            %d bytes" % info["file_size"],
        "width x height:  %d x %d" % (info["width"], info["height"]),
        "mipmap levels:   %d" % info["mipmaps"],
        "pixel format:    %s" % info["pixel_format"],
    ]
    if info["depth"] is not None:
        lines.append("depth:           %d" % info["depth"])
    if info["fourcc"]:
        lines.append("fourcc:          %s" % info["fourcc"])
    if info["dx10"]:
        d = info["dx10"]
        lines += [
            "dxgi format:     %s (#%d)" % (d["dxgi_format"], d["dxgi_format_id"]),
            "resource dim:    %s (array size %d)" % (d["resource_dimension"], d["array_size"]),
            "alpha mode:      %s" % d["alpha_mode"],
        ]
    lines += [
        "header flags:    %s" % info["header_flags"],
        "pf flags:        %s" % info["pf_flags"],
        "pitch/linearsz:  %d" % info["pitch_or_linear_size"],
        "caps:            %s" % info["caps"],
        "caps2:           %s" % info["caps2"],
    ]
    return "\n".join(lines)


def build_dds(width, height, mips=1, fourcc=b"\x00\x00\x00\x00", pf_flags=0x40,
              rgb_bits=0, masks=(0, 0, 0, 0), dx10=None, depth=0):
    """构造一个合法的 DDS 文件字节串(用于 --make-sample 与自测)。"""
    flags = 0x1 | 0x2 | 0x4 | 0x1000
    if mips > 1:
        flags |= 0x20000
    if fourcc != b"\x00\x00\x00\x00" or dx10 is not None:
        flags |= 0x80000
    else:
        flags |= 0x8
    if depth:
        flags |= 0x800000
    caps = 0x1000
    if mips > 1:
        caps |= 0x8 | 0x400000
    hdr = struct.pack("<7I", HEADER_SIZE, flags, height, width,
                      ((width + 3) // 4) * ((height + 3) // 4) * 8, depth,
                      mips if mips > 1 else 0)
    hdr += b"\x00" * 44  # dwReserved1[11]
    hdr += struct.pack("<8I", 32, pf_flags, struct.unpack("<I", fourcc)[0],
                       rgb_bits, masks[0], masks[1], masks[2], masks[3])
    hdr += struct.pack("<5I", caps, 0, 0, 0, 0)
    if dx10 is not None:
        hdr += struct.pack("<5I", *dx10)
    return MAGIC + hdr


def make_sample():
    """示例：64x64 DXT1 带 7 级 mipmap 链。"""
    return build_dds(64, 64, mips=7, fourcc=b"DXT1", pf_flags=0x4)


def selftest():
    checks = 0

    def ok(msg):
        nonlocal checks
        checks += 1
        print("  [ok] %s" % msg)

    # 1) DXT1 + mipmap 链
    info = parse_dds(build_dds(64, 64, mips=7, fourcc=b"DXT1", pf_flags=0x4))
    assert (info["width"], info["height"], info["mipmaps"]) == (64, 64, 7), info
    assert info["fourcc"] == "DXT1" and info["pixel_format"] == "DXT1", info
    ok("DXT1 64x64 with 7 mipmaps")

    # 2) DX10 扩展头 (DXGI 99 = BC7_UNORM_SRGB, 数组 4 层)
    info = parse_dds(build_dds(128, 256, fourcc=b"DX10", pf_flags=0x4,
                               dx10=(99, 3, 0, 4, 0)))
    assert info["dx10"]["dxgi_format"] == "BC7_UNORM_SRGB", info
    assert info["dx10"]["array_size"] == 4 and info["mipmaps"] == 1, info
    ok("DX10 extension -> DXGI BC7_UNORM_SRGB, array size 4")

    # 3) 未压缩 A8R8G8B8（靠掩码识别）
    info = parse_dds(build_dds(16, 16, pf_flags=0x40 | 0x1, rgb_bits=32,
                               masks=(0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)))
    assert info["pixel_format"] == "A8R8G8B8", info
    ok("uncompressed A8R8G8B8 identified via masks")

    # 4) 临时文件全链路（写盘 -> 读回 -> 解析 -> 文本/JSON 输出）
    with tempfile.NamedTemporaryFile(suffix=".dds", delete=False) as fh:
        fh.write(make_sample())
        path = fh.name
    try:
        with open(path, "rb") as fh:
            info = parse_dds(fh.read())
        assert (info["width"], info["height"]) == (64, 64), info
        assert "mipmap levels:   7" in format_text(dict(info, path=path))
        assert json.loads(json.dumps(info))["mipmaps"] == 7
        ok("temp-file round-trip, text+json output")
    finally:
        os.unlink(path)

    # 5) 非法输入必须报错
    for bad in (b"NOTD" + b"\x00" * 200, MAGIC):
        try:
            parse_dds(bad)
        except DDSError:
            pass
        else:
            raise AssertionError("bad input accepted: %r" % bad[:8])
    ok("garbage/truncated input rejected")

    print("selftest PASS (%d checks)" % checks)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="dds-header-read",
        description="解析 DDS 文件头, 输出宽高、mipmap 层数与像素格式")
    parser.add_argument("file", nargs="?", help=".dds 文件路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--make-sample", metavar="OUT",
                        help="生成示例 DXT1 贴图到 OUT 后退出")
    parser.add_argument("--selftest", action="store_true",
                        help="运行内置自测后退出")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.make_sample:
        blob = make_sample()
        with open(args.make_sample, "wb") as fh:
            fh.write(blob)
        print("wrote %d-byte sample DDS to %s" % (len(blob), args.make_sample))
        return 0
    if not args.file:
        parser.error("need a .dds file (or --selftest / --make-sample)")
    try:
        with open(args.file, "rb") as fh:
            info = parse_dds(fh.read())
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    except DDSError as exc:
        print("error: %s: %s" % (args.file, exc), file=sys.stderr)
        return 1
    info["path"] = args.file
    print(json.dumps(info, indent=2) if args.json else format_text(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
