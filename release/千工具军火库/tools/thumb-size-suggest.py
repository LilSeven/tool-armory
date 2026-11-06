#!/usr/bin/env python3
"""缩略图尺寸建议（thumb-size-suggest）。

依据原图尺寸，从常用缩略图方案（16/32/120/320/640/1024 等）中筛选：
1) 不会放大：目标边长不超过原图对应边长（长边模式/宽度模式）；
2) 比例合适：换算后的宽高比与原比例的偏差在容差内（默认 1%）。

示例:
    python thumb-size-suggest.py 1920 1080
    python thumb-size-suggest.py 1920x1080 --targets 120,320,640
    python thumb-size-suggest.py photo.jpg --mode width --tol 2
    python thumb-size-suggest.py photo.jpg --json

退出码: 0=有可用建议; 1=没有满足条件的方案; 2=参数错误。
支持 PNG/JPEG/GIF/BMP/WEBP/TIFF 文件头解析，仅用 Python 标准库。
"""

import argparse
import json
import math
import os
import struct
import sys
import unicodedata

# --------------------------------------------------------------------------
# 图片头解析（只取格式与宽高）
# --------------------------------------------------------------------------

def _jpeg_size(data):
    """扫描 JPEG 段直到 SOF0..SOF15，返回 (宽, 高)。"""
    i, n = 2, len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            break
        while i < n and data[i] == 0xFF:
            i += 1
        if i >= n:
            break
        marker = data[i]
        i += 1
        if marker == 0x01 or 0xD0 <= marker <= 0xD9:  # 无长度段（RST/SOI/EOI 等）
            if marker == 0xD9:
                break
            continue
        if i + 2 > n:
            break
        seglen = struct.unpack_from(">H", data, i)[0]
        if seglen < 2 or i + seglen > n:
            break
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC) and seglen >= 7:
            height = struct.unpack_from(">H", data, i + 3)[0]
            width = struct.unpack_from(">H", data, i + 5)[0]
            return width, height
        i += seglen
    raise ValueError("JPEG 头中未找到 SOF 尺寸段")


def _tiff_size(data):
    """解析 TIFF IFD0 的 ImageWidth/ImageLength 标签，返回 (宽, 高)。"""
    if len(data) < 8 or data[:2] not in (b"II", b"MM"):
        raise ValueError("不是 TIFF 结构")
    bo = "<" if data[:2] == b"II" else ">"
    if struct.unpack_from(bo + "H", data, 2)[0] != 42:
        raise ValueError("TIFF 魔数不符")
    ifd0 = struct.unpack_from(bo + "I", data, 4)[0]
    if ifd0 <= 0 or ifd0 + 2 > len(data):
        raise ValueError("TIFF IFD 偏移越界")
    count = struct.unpack_from(bo + "H", data, ifd0)[0]
    if not 0 < count <= 1024:
        raise ValueError("TIFF IFD 条目数异常")
    sizes = {1: 1, 3: 2, 4: 4}
    w = h = None
    p = ifd0 + 2
    for _ in range(count):
        if p + 12 > len(data):
            break
        tag, typ, cnt = struct.unpack_from(bo + "HHI", data, p)
        vf = data[p + 8:p + 12]
        p += 12
        size = sizes.get(typ)
        if size is None:
            continue
        total = size * cnt
        if total <= 4:
            raw = vf[:total]
        else:
            vo = struct.unpack_from(bo + "I", vf)[0]
            if vo + total > len(data):
                continue
            raw = data[vo:vo + total]
        try:
            val = struct.unpack(bo + {1: "B", 3: "H", 4: "I"}[typ] * cnt, raw)[0]
        except struct.error:
            continue
        if tag == 0x0100 and w is None:
            w = val
        elif tag == 0x0101 and h is None:
            h = val
    if w is None or h is None:
        raise ValueError("TIFF 中缺少尺寸标签")
    return w, h


def read_image_size(path):
    """从文件头读取 (格式, 宽, 高)；无法识别时抛 ValueError。"""
    with open(path, "rb") as fh:
        data = fh.read()
    head = data[:12]
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return ("PNG", struct.unpack_from(">I", data, 16)[0],
                struct.unpack_from(">I", data, 20)[0])
    if head[:2] == b"\xff\xd8":
        w, h = _jpeg_size(data)
        return "JPEG", w, h
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "GIF", struct.unpack_from("<H", data, 6)[0], struct.unpack_from("<H", data, 8)[0]
    if head[:2] == b"BM" and len(data) >= 26:
        hsize = struct.unpack_from("<I", data, 14)[0]
        if hsize == 12:  # BITMAPCOREHEADER
            return "BMP", struct.unpack_from("<H", data, 18)[0], struct.unpack_from("<H", data, 20)[0]
        return ("BMP", abs(struct.unpack_from("<i", data, 18)[0]),
                abs(struct.unpack_from("<i", data, 22)[0]))
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        off = 12
        while off + 8 <= len(data):
            fourcc = data[off:off + 4]
            csize = struct.unpack_from("<I", data, off + 4)[0]
            body = data[off + 8:off + 8 + csize]
            if fourcc == b"VP8X" and len(body) >= 10:
                return ("WEBP", 1 + (body[4] | body[5] << 8 | body[6] << 16),
                        1 + (body[7] | body[8] << 8 | body[9] << 16))
            if fourcc == b"VP8 " and len(body) >= 10 and body[3:6] == b"\x9d\x01\x2a":
                return ("WEBP", struct.unpack_from("<H", body, 6)[0] & 0x3FFF,
                        struct.unpack_from("<H", body, 8)[0] & 0x3FFF)
            if fourcc == b"VP8L" and len(body) >= 5 and body[0] == 0x2F:
                bits = int.from_bytes(body[1:5], "little")
                return "WEBP", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            off += 8 + csize + (csize & 1)
        raise ValueError("WEBP 中未找到尺寸块")
    if head[:2] in (b"II", b"MM"):
        w, h = _tiff_size(data)
        return "TIFF", w, h
    raise ValueError("无法识别的图片格式")


# --------------------------------------------------------------------------
# 展示辅助（全角字符按 2 列宽对齐）
# --------------------------------------------------------------------------

def dwidth(text):
    return sum(2 if unicodedata.east_asian_width(ch) in "FW" else 1 for ch in text)


def pad(text, width, right=False):
    gap = " " * max(0, width - dwidth(text))
    return gap + text if right else text + gap


# --------------------------------------------------------------------------
# 主体逻辑
# --------------------------------------------------------------------------

DEFAULT_TARGETS = [16, 24, 32, 48, 64, 96, 120, 128, 160, 200, 240, 256,
                   320, 384, 480, 512, 640, 800, 1024]


def parse_source(parts):
    """把命令行来源解析为 (宽, 高, 来源描述, 文件格式或 None)。"""
    if len(parts) == 2:
        try:
            return int(parts[0]), int(parts[1]), "参数", None
        except ValueError:
            raise ValueError("两个位置参数必须是整数宽高，例如: 1920 1080")
    spec = parts[0]
    if os.path.isfile(spec):
        fmt, w, h = read_image_size(spec)
        return w, h, spec, fmt
    txt = spec.lower().replace("×", "x").replace("*", "x")
    a, sep, b = txt.partition("x")
    if sep:
        try:
            return int(a), int(b), "参数", None
        except ValueError:
            pass
    raise ValueError("无法解析来源: %r（支持 宽 高 / WxH / 图片文件路径）" % spec)


def suggest(w, h, targets, mode, tol):
    """对每个目标边长评估：是否放大、换算尺寸、比例偏差。"""
    ratio = w / h
    ref = max(w, h) if mode == "long" else w
    rows = []
    for t in targets:
        if mode == "long" and h > w:      # 竖图：目标为高度
            nh = t
            nw = max(1, int(t * w / h + 0.5))
        else:                             # 横图/方图或宽度模式：目标为宽度
            nw = t
            nh = max(1, int(t * h / w + 0.5))
        upscaled = t > ref
        dev = abs((nw / nh) / ratio - 1.0) * 100.0
        if upscaled:
            verdict = "放大"
        elif dev > tol:
            verdict = "比例偏差"
        else:
            verdict = "OK"
        rows.append({"target": t, "width": nw, "height": nh,
                     "scale_pct": round(t / ref * 100.0, 1),
                     "dev_pct": round(dev, 2), "verdict": verdict})
    return rows


def ratio_text(w, h):
    g = math.gcd(w, h)
    rw, rh = w // g, h // g
    return "%d:%d" % (rw, rh) if rw <= 100 and rh <= 100 else None


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(
        prog="thumb-size-suggest", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="+",
                    help="原图尺寸: 宽 高 两个整数、WxH 形式、或图片文件路径")
    ap.add_argument("-t", "--targets", default=",".join(map(str, DEFAULT_TARGETS)),
                    help="逗号分隔的目标边长列表（默认 16,24,...,1024）")
    ap.add_argument("-m", "--mode", choices=("long", "width"), default="long",
                    help="long=目标为长边(默认), width=目标为宽度")
    ap.add_argument("--tol", type=float, default=1.0, metavar="PCT",
                    help="比例偏差容差百分比（默认 1.0）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    try:
        targets = [int(x) for x in args.targets.split(",") if x.strip()]
    except ValueError:
        print("错误: --targets 必须是逗号分隔的整数", file=sys.stderr)
        return 2
    if not targets or any(t < 1 for t in targets):
        print("错误: 目标边长必须是正整数", file=sys.stderr)
        return 2
    try:
        w, h, src, fmt = parse_source(args.source)
    except (ValueError, OSError) as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 2
    if not 1 <= w <= 1000000 or not 1 <= h <= 1000000:
        print("错误: 尺寸超出合理范围: %dx%d" % (w, h), file=sys.stderr)
        return 2

    rows = suggest(w, h, targets, args.mode, args.tol)
    ok_rows = [r for r in rows if r["verdict"] == "OK"]
    ratio = ratio_text(w, h)

    if args.json:
        doc = {"source": {"width": w, "height": h, "source": src, "format": fmt,
                          "ratio": ratio, "ratio_value": round(w / h, 4)},
               "mode": args.mode, "tolerance_pct": args.tol,
               "recommended": [{"target": r["target"], "width": r["width"],
                                "height": r["height"]} for r in ok_rows],
               "candidates": rows}
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0 if ok_rows else 1

    print("原图: %dx%d  比例 %s (%.3f)  来源: %s" %
          (w, h, ratio or "-", w / h, "%s (%s)" % (src, fmt) if fmt else src))
    print("模式: %s  容差: %.1f%%  候选: %d 个" %
          ("长边对齐" if args.mode == "long" else "宽度对齐", args.tol, len(rows)))
    print()
    print(pad("目标", 6) + pad("输出尺寸", 10) + pad("缩放", 8) +
          pad("比例偏差", 10) + "判定")
    print("-" * 46)
    for r in rows:
        print(pad(str(r["target"]), 6) +
              pad("%dx%d" % (r["width"], r["height"]), 10) +
              pad("%.1f%%" % r["scale_pct"], 8) +
              pad("%.2f%%" % r["dev_pct"], 10) + r["verdict"])
    print("-" * 46)
    if ok_rows:
        print("可用方案 %d/%d: %s" % (len(ok_rows), len(rows),
              ", ".join(str(r["target"]) for r in ok_rows)))
        return 0
    print("没有满足条件的方案（全部会放大或比例偏差超容差）。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
