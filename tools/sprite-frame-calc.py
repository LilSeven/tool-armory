#!/usr/bin/env python3
"""雪碧图切格计算（sprite-frame-calc）。

给定雪碧图总尺寸与行列数，计算每格尺寸、每格左上角偏移坐标，
并校验总尺寸能否被行列数整除。

示例:
    python sprite-frame-calc.py --sheet 1024x768 --cols 4 --rows 3
    python sprite-frame-calc.py -s sheet.png -c 8 -r 2 --json
    python sprite-frame-calc.py -s 1000x750 -c 3 -r 3 --start 1 --limit 5

说明:
  - --sheet 支持 WxH 形式或图片文件路径（自动读文件头取尺寸，
    支持 PNG/JPEG/GIF/BMP/WEBP/TIFF）;
  - 不整除时仍按向下取整输出每格尺寸与坐标，并给出建议画布尺寸，退出码 1;
  - --json 输出机器可读结果（含全部帧坐标）。
退出码: 0=整除校验通过; 1=不整除; 2=参数错误。
仅用 Python 标准库。
"""

import argparse
import json
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
        if marker == 0x01 or 0xD0 <= marker <= 0xD9:
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
        if hsize == 12:
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

def parse_sheet(spec):
    """把 --sheet 解析为 (来源描述, 格式, 宽, 高)。"""
    if os.path.isfile(spec):
        fmt, w, h = read_image_size(spec)
        return spec, fmt, w, h
    txt = spec.lower().replace("×", "x").replace("*", "x")
    a, sep, b = txt.partition("x")
    if sep:
        try:
            return spec, "参数", int(a), int(b)
        except ValueError:
            pass
    raise ValueError("无法解析雪碧图尺寸: %r（支持 WxH 或图片文件路径）" % spec)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(
        prog="sprite-frame-calc", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-s", "--sheet", required=True, help="雪碧图尺寸 WxH 或图片文件路径")
    ap.add_argument("-c", "--cols", type=int, required=True, help="列数（横向帧数）")
    ap.add_argument("-r", "--rows", type=int, required=True, help="行数（纵向帧数）")
    ap.add_argument("--start", type=int, default=0, help="帧编号起始值（默认 0）")
    ap.add_argument("--limit", type=int, default=0, help="表格最多打印的帧数（0=全部）")
    ap.add_argument("--json", action="store_true", help="输出 JSON（含全部帧坐标）")
    args = ap.parse_args(argv)

    if args.cols < 1 or args.rows < 1:
        print("错误: --cols/--rows 必须为正整数", file=sys.stderr)
        return 2
    if args.start < 0 or args.limit < 0:
        print("错误: --start/--limit 不能为负", file=sys.stderr)
        return 2
    try:
        src, fmt, w, h = parse_sheet(args.sheet)
    except (ValueError, OSError) as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 2
    if w < 1 or h < 1:
        print("错误: 雪碧图尺寸必须为正: %dx%d" % (w, h), file=sys.stderr)
        return 2

    fw, rx = divmod(w, args.cols)
    fh_, ry = divmod(h, args.rows)
    divisible = rx == 0 and ry == 0
    frames = [{"index": args.start + r * args.cols + c, "row": r, "col": c,
               "x": c * fw, "y": r * fh_}
              for r in range(args.rows) for c in range(args.cols)]

    doc = {"sheet": {"width": w, "height": h, "source": src, "format": fmt},
           "cols": args.cols, "rows": args.rows,
           "frame": {"width": fw, "height": fh_},
           "total_frames": len(frames), "start_index": args.start,
           "divisible": divisible, "remainder_x": rx, "remainder_y": ry,
           "frames": frames}
    if args.json:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0 if divisible else 1

    print("雪碧图: %dx%d (%s)   列=%d 行=%d" % (w, h, fmt, args.cols, args.rows))
    print("每格: %dx%d   总帧数: %d" % (fw, fh_, len(frames)))
    if divisible:
        print("整除校验: 通过 (%d/%d=%d, %d/%d=%d)" %
              (w, args.cols, fw, h, args.rows, fh_))
    else:
        print("整除校验: 不通过")
        if rx:
            print("  水平: %d/%d = %d 余 %d → 建议画布宽 %d(每格%d) 或 %d(每格%d)" %
                  (w, args.cols, fw, rx,
                   args.cols * fw, fw, args.cols * (fw + 1), fw + 1))
        if ry:
            print("  垂直: %d/%d = %d 余 %d → 建议画布高 %d(每格%d) 或 %d(每格%d)" %
                  (h, args.rows, fh_, ry,
                   args.rows * fh_, fh_, args.rows * (fh_ + 1), fh_ + 1))
        print("已按向下取整计算；水平余 %d px、垂直余 %d px 将成为最后一列/行的留白。" % (rx, ry))
    print()
    cols_def = [("帧", [str(f["index"]) for f in frames]),
                ("行", [str(f["row"]) for f in frames]),
                ("列", [str(f["col"]) for f in frames]),
                ("X偏移", [str(f["x"]) for f in frames]),
                ("Y偏移", [str(f["y"]) for f in frames])]
    widths = [max(dwidth(head), max(len(v) for v in vals)) for head, vals in cols_def]
    print("  ".join(pad(head, wd, right=True) for (head, _), wd in zip(cols_def, widths)))
    shown = frames if args.limit <= 0 else frames[:args.limit]
    for f in shown:
        cells = (str(f["index"]), str(f["row"]), str(f["col"]), str(f["x"]), str(f["y"]))
        print("  ".join(pad(c, wd, right=True) for c, wd in zip(cells, widths)))
    if args.limit and len(frames) > args.limit:
        print("  ...（共 %d 帧，仅显示前 %d 行，--json 可获取全部坐标）" % (len(frames), args.limit))
    return 0 if divisible else 1


if __name__ == "__main__":
    sys.exit(main())
