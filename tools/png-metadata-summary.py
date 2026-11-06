#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG 元数据汇总器：解析 PNG 的辅助信息块并以人类可读方式汇总输出。

覆盖的块：IHDR（基本信息）、gAMA、cHRM、sRGB、iCCP、pHYs、bKGD、tRNS、tIME、
tEXt/zTXt/iTXt（关键字清单），以及 PLTE/IDAT 统计和其余未识别的辅助块。
各字段的解码均做防御式处理：坏数据不会导致崩溃，只输出警告行。

用法：
    python png-metadata-summary.py <image.png>

退出码：
    0 = 正常
    2 = 文件不存在 / 无法读取 / 不是 PNG / PNG 结构损坏

示例：
    python png-metadata-summary.py photo.png
"""

import argparse
import struct
import sys
import zlib

PNG_SIG = b"\x89PNG\r\n\x1a\n"
INCH_M = 0.0254

COLOR_TYPES = {0: "灰度", 2: "真彩 RGB", 3: "调色板",
               4: "灰度+Alpha", 6: "真彩 RGB+Alpha"}
SRGB_INTENTS = ["perceptual（感知）", "relative colorimetric（相对比色）",
                "saturation（饱和度）", "absolute colorimetric（绝对比色）"]
HANDLED = {b"IHDR", b"IDAT", b"IEND", b"PLTE", b"gAMA", b"cHRM", b"sRGB",
           b"iCCP", b"pHYs", b"bKGD", b"tRNS", b"tIME",
           b"tEXt", b"zTXt", b"iTXt"}


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
    ap = argparse.ArgumentParser(description="汇总 PNG 辅助块（元数据），人类可读输出")
    ap.add_argument("file", help="PNG 文件路径")
    args = ap.parse_args(argv)

    try:
        with open(args.file, "rb") as fh:
            data = fh.read()
        chunks, warnings = parse_chunks(data)
    except (OSError, ValueError) as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 2

    info = {}
    for raw_type, cdata, _off in chunks:
        info.setdefault(raw_type, []).append(cdata)

    lines = []
    lines.append(("文件", "%s（%d 字节，%d 个 chunk）"
                  % (args.file, len(data), len(chunks))))

    # ---- IHDR ----
    color_type = None
    if b"IHDR" in info:
        raw = info[b"IHDR"][0]
        if len(raw) >= 13:
            w, h, depth, ct, comp, filt, inter = struct.unpack(">IIBBBBB", raw)
            color_type = ct
            if comp or filt:
                warnings.append("IHDR 压缩/过滤方法非 0（%d/%d），不符合规范"
                                % (comp, filt))
            lines.append(("IHDR", "%d x %d 像素，%d bit，颜色类型 %d（%s），%s"
                          % (w, h, depth, ct, COLOR_TYPES.get(ct, "未知"),
                             "Adam7 隔行" if inter else "无隔行")))
        else:
            warnings.append("IHDR 数据仅 %d 字节（规范应为 13）" % len(raw))

    # ---- 色彩特征块 ----
    if b"gAMA" in info:
        raw = info[b"gAMA"][0]
        if len(raw) == 4:
            v = struct.unpack(">I", raw)[0]
            lines.append(("gAMA", "gamma = %d / 100000 = %.5f" % (v, v / 100000)))
        else:
            warnings.append("gAMA 数据 %d 字节（规范应为 4）" % len(raw))

    if b"cHRM" in info:
        raw = info[b"cHRM"][0]
        if len(raw) == 32:
            vals = struct.unpack(">8I", raw)
            lines.append(("cHRM", "白点(%.5f, %.5f) 红(%.5f, %.5f) "
                                  "绿(%.5f, %.5f) 蓝(%.5f, %.5f)"
                          % tuple(v / 100000 for v in vals)))
        else:
            warnings.append("cHRM 数据 %d 字节（规范应为 32）" % len(raw))

    if b"sRGB" in info:
        raw = info[b"sRGB"][0]
        if len(raw) == 1:
            i = raw[0]
            name = SRGB_INTENTS[i] if i < len(SRGB_INTENTS) else "未知意图"
            lines.append(("sRGB", "渲染意图 %d（%s）" % (i, name)))
        else:
            warnings.append("sRGB 数据 %d 字节（规范应为 1）" % len(raw))

    if b"iCCP" in info:
        raw = info[b"iCCP"][0]
        name, sep, rest = raw.partition(b"\x00")
        if sep and len(rest) >= 1:
            method, comp = rest[0], rest[1:]
            try:
                prof = zlib.decompress(comp)
                lines.append(("iCCP", 'ICC 配置文件 "%s"，压缩方法 %d，'
                                      "压缩 %d 字节 → 解压 %d 字节"
                              % (name.decode("latin-1"), method,
                                 len(comp), len(prof))))
            except zlib.error as exc:
                lines.append(("iCCP", 'ICC 配置文件 "%s"，压缩方法 %d，'
                                      "数据无法解压（%s）"
                              % (name.decode("latin-1"), method, exc)))
        else:
            warnings.append("iCCP 格式异常（缺少 NUL 分隔符或压缩方法字节）")

    # ---- 物理信息 ----
    if b"pHYs" in info:
        raw = info[b"pHYs"][0]
        if len(raw) == 9:
            px, py, unit = struct.unpack(">IIB", raw)
            if unit == 1:
                lines.append(("pHYs", "%d x %d px/m（单位=米），DPI %.2f x %.2f"
                              % (px, py, px * INCH_M, py * INCH_M)))
            else:
                lines.append(("pHYs", "%d x %d px/m（单位=未知，仅表示像素宽高比）"
                              % (px, py)))
        else:
            warnings.append("pHYs 数据 %d 字节（规范应为 9）" % len(raw))

    # ---- 背景与透明 ----
    if b"bKGD" in info:
        raw = info[b"bKGD"][0]
        if color_type in (0, 4) and len(raw) == 2:
            lines.append(("bKGD", "背景灰度 = %d" % struct.unpack(">H", raw)[0]))
        elif color_type in (2, 6) and len(raw) == 6:
            r, g, b = struct.unpack(">3H", raw)
            lines.append(("bKGD", "背景 RGB = (%d, %d, %d)" % (r, g, b)))
        elif color_type == 3 and len(raw) == 1:
            lines.append(("bKGD", "背景调色板索引 = %d" % raw[0]))
        else:
            lines.append(("bKGD", "原始 %d 字节：%s（与颜色类型 %s 不匹配）"
                          % (len(raw), raw.hex(), color_type)))

    if b"tRNS" in info:
        raw = info[b"tRNS"][0]
        if color_type is None:
            lines.append(("tRNS", "原始 %d 字节：%s（缺 IHDR，无法按颜色类型解读）"
                          % (len(raw), raw.hex())))
        elif color_type == 0 and len(raw) == 2:
            lines.append(("tRNS", "透明灰度采样值 = %d"
                          % struct.unpack(">H", raw)[0]))
        elif color_type == 2 and len(raw) == 6:
            r, g, b = struct.unpack(">3H", raw)
            lines.append(("tRNS", "透明色 RGB = (%d, %d, %d)" % (r, g, b)))
        elif color_type == 3:
            items = ["%d:%d" % (i, v) for i, v in enumerate(raw)]
            shown = " ".join(items[:8]) + (" ..." if len(items) > 8 else "")
            lines.append(("tRNS", "调色板 Alpha 共 %d 项：%s" % (len(raw), shown)))
        elif color_type in (4, 6):
            lines.append(("tRNS", "存在 %d 字节，但颜色类型 %d 已含完整 Alpha "
                                  "通道（不符合 PNG 规范）" % (len(raw), color_type)))
        else:
            lines.append(("tRNS", "原始 %d 字节：%s（与颜色类型 %d 不匹配）"
                          % (len(raw), raw.hex(), color_type)))

    # ---- 时间 ----
    if b"tIME" in info:
        raw = info[b"tIME"][0]
        if len(raw) == 7:
            yy, mo, dd, hh, mi, ss = struct.unpack(">HBBBBB", raw)
            if 1 <= mo <= 12 and 1 <= dd <= 31 and hh < 24 and mi < 60 and ss < 60:
                lines.append(("tIME", "%04d-%02d-%02d %02d:%02d:%02d（UTC，最后修改时间）"
                              % (yy, mo, dd, hh, mi, ss)))
            else:
                lines.append(("tIME", "字段超出合理范围：%d-%d-%d %d:%d:%d"
                              % (yy, mo, dd, hh, mi, ss)))
        else:
            warnings.append("tIME 数据 %d 字节（规范应为 7）" % len(raw))

    # ---- 调色板 / 图像数据 ----
    if b"PLTE" in info:
        p = info[b"PLTE"][0]
        if len(p) % 3 == 0:
            lines.append(("PLTE", "调色板 %d 项（%d 字节）" % (len(p) // 3, len(p))))
        else:
            lines.append(("PLTE", "%d 字节（不是 3 的倍数，异常）" % len(p)))
    if b"IDAT" in info:
        sizes = [len(d) for d in info[b"IDAT"]]
        lines.append(("IDAT", "%d 块，共 %d 字节（图像数据）"
                      % (len(sizes), sum(sizes))))

    # ---- 文本块清单 ----
    texts = ["%s(%s)" % (d.partition(b"\x00")[0].decode("latin-1", "replace"),
                         t.decode("latin-1"))
             for t, d, _off in chunks if t in (b"tEXt", b"zTXt", b"iTXt")]
    if texts:
        lines.append(("文本块", "%d 个：%s" % (len(texts), ", ".join(texts))))

    # ---- 其余未识别块 ----
    others = {}
    for raw_type, cdata, _off in chunks:
        if raw_type not in HANDLED:
            others.setdefault(raw_type, []).append(len(cdata))
    if others:
        parts = ["%s x%d（共 %d 字节）" % (t.decode("latin-1"), len(sizes), sum(sizes))
                 for t, sizes in sorted(others.items())]
        lines.append(("其他块", "; ".join(parts)))
    else:
        lines.append(("其他块", "无"))

    print("== PNG 元数据汇总 ==")
    for label, text in lines:
        print("%-8s: %s" % (label, text))
    for w in warnings:
        print("警告：%s" % w, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
