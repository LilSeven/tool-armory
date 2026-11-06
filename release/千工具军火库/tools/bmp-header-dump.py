#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bmp-header-dump —— 解析并转储 BMP 的 BITMAPFILEHEADER 与 DIB 头。

读取 BMP 文件,解析 14 字节 BITMAPFILEHEADER 与 DIB 头,输出:DIB 类型
(BITMAPCOREHEADER / BITMAPINFOHEADER / V2 / V3 / OS/2 2.x / V4 / V5)、
宽高(含自顶向下判定)、位面数、位深、压缩方式、调色板项数、像素数据偏移、
行跨度、通道掩码(V2+)等。仅用 Python 标准库。

用法:
    python bmp-header-dump.py [--json] FILE [FILE ...]

示例:
    python bmp-header-dump.py shot.bmp
    python bmp-header-dump.py --json *.bmp

退出码: 0 全部解析成功;1 存在魔数不符(非 BMP)的文件;2 存在截断或读取失败。
"""

import argparse
import glob
import json
import sys

DIB_NAMES = {
    12: "BITMAPCOREHEADER (OS/2 1.x)",
    40: "BITMAPINFOHEADER (Windows 3.x)",
    52: "BITMAPV2INFOHEADER (未公开, Adobe)",
    56: "BITMAPV3INFOHEADER (未公开, Adobe)",
    64: "OS22XBITMAPHEADER (OS/2 2.x)",
    108: "BITMAPV4HEADER",
    124: "BITMAPV5HEADER",
}

COMPRESSION = {
    0: "BI_RGB(不压缩)",
    1: "BI_RLE8 (8bpp RLE)",
    2: "BI_RLE4 (4bpp RLE)",
    3: "BI_BITFIELDS(通道掩码)",
    4: "BI_JPEG",
    5: "BI_PNG",
    6: "BI_ALPHABITFIELDS(带 alpha 掩码)",
    11: "BI_CMYK",
    12: "BI_CMYKRLE8",
    13: "BI_CMYKRLE4",
}

COLORSPACES = {
    0x00000000: "LCS_CALIBRATED_RGB",
    0x73524742: "LCS_sRGB",
    0x57696E20: "LCS_WINDOWS_COLOR_SPACE",
    0x4C494E4B: "LCS_PROFILE_LINKED",
    0x4D424544: "LCS_PROFILE_EMBEDDED",
}


def setup_stdio():
    """Windows 管道/重定向下强制 UTF-8 输出,避免 GBK 编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def parse_bmp(data):
    """成功返回 (info_dict, warnings, None);失败返回 (None, [], 错误说明)。"""
    warnings = []
    if len(data) < 2 or data[:2] != b"BM":
        return None, [], "不是 BMP:头部字节=%r(应为 b'BM')" % data[:2]
    if len(data) < 18:
        return None, [], "文件过短(%d 字节),读不到 DIB 头大小字段" % len(data)

    u16 = lambda o: int.from_bytes(data[o:o + 2], "little")
    u32 = lambda o: int.from_bytes(data[o:o + 4], "little")
    i32 = lambda o: int.from_bytes(data[o:o + 4], "little", signed=True)

    fs_field, r1, r2, data_off = u32(2), u16(6), u16(8), u32(10)
    dib = u32(14)
    info = {"signature": "BM", "file_size_field": fs_field,
            "reserved": [r1, r2], "pixel_data_offset": data_off,
            "dib_size": dib, "file_size_actual": len(data)}
    if fs_field != len(data):
        warnings.append("文件大小字段=%d 与实际 %d 字节不一致" % (fs_field, len(data)))
    if data_off > len(data):
        warnings.append("像素数据偏移 %d 超出文件长度 %d" % (data_off, len(data)))

    clr_used = None
    if dib == 12:
        if len(data) < 26:
            return None, [], "BITMAPCOREHEADER 需 26 字节,文件仅 %d" % len(data)
        info.update({"dib_type": DIB_NAMES[12], "width": u16(18),
                     "height": u16(20), "planes": u16(22), "bpp": u16(24)})
    elif 16 <= dib < 40:
        # OS/2 2.x 变体:宽高为无符号 32 位,部分字段可能缺失
        if len(data) < 14 + min(dib, 30):
            return None, [], "DIB 头声明 %d 字节,文件仅 %d" % (dib, len(data))
        info.update({"dib_type": "OS/2 2.x DIB (size=%d,部分解析)" % dib,
                     "width": u32(18), "height": u32(22)})
        if len(data) >= 28:
            info["planes"] = u16(26)
        if len(data) >= 30:
            info["bpp"] = u16(28)
    elif dib >= 40:
        if len(data) < 54:
            return None, [], "DIB 头声明 %d 字节,但文件仅 %d(至少需 54)" % (dib, len(data))
        info.update({"dib_type": DIB_NAMES.get(dib, "未知 DIB 头 (size=%d)" % dib),
                     "width": i32(18), "height": i32(22),
                     "planes": u16(26), "bpp": u16(28),
                     "compression_code": u32(30), "image_size": u32(34),
                     "x_ppm": i32(38), "y_ppm": i32(42),
                     "clr_used": u32(46), "clr_important": u32(50)})
        clr_used = info["clr_used"]
        if dib >= 52 and len(data) >= 14 + 52:
            masks = {"red": u32(54), "green": u32(58), "blue": u32(62)}
            if dib >= 56 and len(data) >= 14 + 56:
                masks["alpha"] = u32(66)
            info["channel_masks"] = masks
        if dib >= 108 and len(data) >= 14 + 74:
            cs = u32(70)
            info["colorspace"] = {"code": cs,
                                  "name": COLORSPACES.get(cs, "未知/未列出")}
        if dib >= 124 and len(data) >= 14 + 130:
            info["v5"] = {"intent": u32(118), "profile_data": u32(122),
                          "profile_size": u32(126)}
    else:
        return None, [], "DIB 头大小 %d 无法识别(<40 且非 12/16..39)" % dib

    bpp = info.get("bpp")
    if not bpp:
        return None, [], "无法确定位深(bpp=%r)" % bpp

    if clr_used:
        info["palette_entries"] = clr_used
        info["palette_note"] = "clr_used=%d" % clr_used
    elif clr_used is None:
        info["palette_entries"] = 1 << bpp
        info["palette_note"] = "无 clr_used 字段,按 %dbpp 推断 2^%d=%d" % (
            bpp, bpp, 1 << bpp)
    else:
        info["palette_entries"] = (1 << bpp) if bpp <= 8 else 0
        info["palette_note"] = "clr_used=0,按 %dbpp 推断" % bpp

    if isinstance(info["height"], int) and info["height"] < 0:
        info["height_abs"] = -info["height"]
        info["orientation"] = "自顶向下 top-down(高度为负)"
    else:
        info["height_abs"] = info["height"]
        info["orientation"] = "自底向上 bottom-up"
    info["row_stride"] = ((abs(info["width"]) * bpp + 31) // 32) * 4
    return info, warnings, None


def render(rec):
    lines = ["文件: %s (%d 字节)" % (rec["file"], rec["file_size_actual"])]
    lines.append("  BITMAPFILEHEADER:")
    lines.append("    标识: %s | 文件大小字段: %d | 保留: 0x%04X,0x%04X | 像素数据偏移: %d"
                 % (rec["signature"], rec["file_size_field"], rec["reserved"][0],
                    rec["reserved"][1], rec["pixel_data_offset"]))
    lines.append("  DIB 头:")
    lines.append("    类型: %s (%d 字节)" % (rec["dib_type"], rec["dib_size"]))
    lines.append("    宽 x 高: %d x %d (%s)"
                 % (rec["width"], rec["height_abs"], rec["orientation"]))
    lines.append("    位面数: %s | 位深: %s bpp" % (rec.get("planes", "?"), rec["bpp"]))
    if "compression_code" in rec:
        lines.append("    压缩: %s (code=%d)"
                     % (COMPRESSION.get(rec["compression_code"], "未知"),
                        rec["compression_code"]))
        lines.append("    图像数据大小字段: %d 字节 | 分辨率: %d x %d 像素/米 | 重要颜色: %d"
                     % (rec["image_size"], rec["x_ppm"], rec["y_ppm"],
                        rec["clr_important"]))
    lines.append("    调色板项数: %d (%s)" % (rec["palette_entries"], rec["palette_note"]))
    lines.append("    行跨度(4 字节对齐): %d 字节" % rec["row_stride"])
    if "channel_masks" in rec:
        m = rec["channel_masks"]
        s = "    通道掩码: R=0x%08X G=0x%08X B=0x%08X" % (m["red"], m["green"], m["blue"])
        if "alpha" in m:
            s += " A=0x%08X" % m["alpha"]
        lines.append(s)
    if "colorspace" in rec:
        lines.append("    颜色空间: %s (0x%08X)"
                     % (rec["colorspace"]["name"], rec["colorspace"]["code"]))
    if "v5" in rec:
        v = rec["v5"]
        lines.append("    V5 附加: intent=%d profile_data=%d profile_size=%d"
                     % (v["intent"], v["profile_data"], v["profile_size"]))
    for wmsg in rec["warnings"]:
        lines.append("  [警告] " + wmsg)
    return "\n".join(lines)


def expand_inputs(raw):
    paths = []
    for arg in raw:
        if "*" in arg or "?" in arg:
            hits = sorted(glob.glob(arg))
            if not hits:
                print("没有匹配到文件: %s" % arg, file=sys.stderr)
                raise SystemExit(2)
            paths.extend(hits)
        else:
            paths.append(arg)
    return paths


def main(argv=None):
    setup_stdio()
    ap = argparse.ArgumentParser(
        prog="bmp-header-dump.py",
        description="解析 BMP 的 BITMAPFILEHEADER 与 DIB 头并转储(详见文件顶部 docstring)。",
    )
    ap.add_argument("files", nargs="+", metavar="FILE", help="BMP 文件,支持通配符")
    ap.add_argument("--json", action="store_true", help="以 JSON 数组输出")
    args = ap.parse_args(argv)

    results, any_notbmp, any_broken = [], False, False
    for path in expand_inputs(args.files):
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            results.append({"file": path, "error": str(exc)})
            any_broken = True
            continue
        info, warnings, fatal = parse_bmp(data)
        if info is None:
            results.append({"file": path, "error": fatal})
            if fatal.startswith("不是 BMP"):
                any_notbmp = True
            else:
                any_broken = True
        else:
            rec = {"file": path}
            rec.update(info)
            rec["warnings"] = warnings
            results.append(rec)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for rec in results:
            if "dib_type" not in rec:
                print("%s: 解析失败(%s)" % (rec["file"], rec["error"]))
            else:
                print(render(rec))
    return 2 if any_broken else (1 if any_notbmp else 0)


if __name__ == "__main__":
    sys.exit(main())
