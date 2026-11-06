#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""比例条件筛选 —— 按宽高比 (ratio = 宽/高) 区间筛选目录中的图片。

仅解析图片文件头获取尺寸（不解码像素、不依赖第三方库），支持
PNG / JPEG / GIF / BMP / WebP / TIFF。只用 Python 标准库。

条件（可同时给多个，取交集）:
  --portrait [R]    竖版: ratio < 1（可加阈值，如 --portrait 0.8 表示 ratio < 0.8）
  --landscape [R]   横版: ratio > 1（可加阈值，如 --landscape 1.2 表示 ratio > 1.2）
  --square          方形: |ratio - 1| <= --tol（默认容差 0.01）
  --min R           ratio 下限（含）
  --max R           ratio 上限（含）

选项:
  -r, --recursive   递归扫描子目录
  --ext LIST        扩展名，逗号分隔（默认 png,jpg,jpeg,gif,bmp,webp,tif,tiff；'*' 表示所有文件）
  -v, --verbose     同时列出无法解析的文件

示例命令:
  python img-filter-ratio.py D:/pics --portrait
  python img-filter-ratio.py D:/pics --landscape 1.2
  python img-filter-ratio.py D:/pics --min 0.9 --max 1.1 --recursive
  python img-filter-ratio.py D:/pics --square -v

退出码: 0 正常（含无匹配）；2 参数或目录错误。
限制: 仅凭文件头解析，极端构造（超大 EXIF 前缀、损坏头部等）可能无法识别。
"""

import argparse
import os
import struct
import sys

DEFAULT_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff")
_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _png_dims(head):
    if len(head) < 24 or head[12:16] != b"IHDR":
        return (0, 0)
    return struct.unpack(">II", head[16:24])


def _gif_dims(head):
    if len(head) < 10:
        return (0, 0)
    return struct.unpack("<HH", head[6:10])


def _bmp_dims(head):
    if len(head) < 26:
        return (0, 0)
    hdr_size = struct.unpack("<I", head[14:18])[0]
    if hdr_size == 12:  # BITMAPCOREHEADER
        if len(head) < 22:
            return (0, 0)
        return struct.unpack("<HH", head[18:22])
    w, h = struct.unpack("<ii", head[18:26])
    return (w, abs(h))  # h 可为负（自顶向下存储）


def _webp_dims(head):
    off = 12
    while off + 8 <= len(head):
        fourcc = head[off:off + 4]
        size = struct.unpack("<I", head[off + 4:off + 8])[0]
        data = head[off + 8:off + 8 + size]
        if fourcc == b"VP8 " and len(data) >= 10 and data[3:6] == b"\x9d\x01\x2a":
            w = struct.unpack("<H", data[6:8])[0] & 0x3FFF
            h = struct.unpack("<H", data[8:10])[0] & 0x3FFF
            return (w, h)
        if fourcc == b"VP8L" and len(data) >= 5 and data[0] == 0x2F:
            bits = struct.unpack("<I", data[1:5])[0]
            return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        if fourcc == b"VP8X" and len(data) >= 10:
            return (int.from_bytes(data[4:7], "little") + 1,
                    int.from_bytes(data[7:10], "little") + 1)
        off += 8 + size + (size & 1)
    return (0, 0)


def _tiff_dims(head):
    endian = "<" if head[:2] == b"II" else ">"
    if len(head) < 8:
        return (0, 0)
    ifd = struct.unpack(endian + "I", head[4:8])[0]
    if ifd + 2 > len(head):
        return (0, 0)
    n = struct.unpack(endian + "H", head[ifd:ifd + 2])[0]
    w = h = 0
    for i in range(n):
        ent = ifd + 2 + i * 12
        if ent + 12 > len(head):
            return (0, 0)
        tag, typ, cnt = struct.unpack(endian + "HHI", head[ent:ent + 8])
        if tag in (256, 257) and cnt == 1:
            if typ == 3:      # SHORT
                val = struct.unpack(endian + "H", head[ent + 8:ent + 10])[0]
            elif typ == 4:    # LONG
                val = struct.unpack(endian + "I", head[ent + 8:ent + 12])[0]
            else:
                continue
            if tag == 256:
                w = val
            else:
                h = val
    return (w, h)


def _jpeg_dims(f):
    f.seek(2)
    while True:
        b = f.read(1)
        if not b:
            return (0, 0)
        if b != b"\xff":
            continue
        marker = 0xFF
        while marker == 0xFF:
            m = f.read(1)
            if not m:
                return (0, 0)
            marker = m[0]
        if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
            continue
        if marker in (0xD9, 0xDA):  # EOI / SOS：SOF 必在其前
            return (0, 0)
        seg = f.read(2)
        if len(seg) < 2:
            return (0, 0)
        seg_len = struct.unpack(">H", seg)[0]
        if seg_len < 2:
            return (0, 0)
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            data = f.read(5)
            if len(data) < 5:
                return (0, 0)
            _, h, w = struct.unpack(">BHH", data)
            return (w, h)
        f.seek(seg_len - 2, 1)


def _head_dims(head):
    if head[:8] == _PNG_SIG and head[12:16] == b"IHDR":
        w, h = _png_dims(head)
        return ("PNG", w, h)
    if head[:6] in (b"GIF87a", b"GIF89a"):
        w, h = _gif_dims(head)
        return ("GIF", w, h)
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        w, h = _webp_dims(head)
        return ("WebP", w, h)
    if head[:2] == b"BM":
        w, h = _bmp_dims(head)
        return ("BMP", w, h)
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        w, h = _tiff_dims(head)
        return ("TIFF", w, h)
    return ("", 0, 0)


def read_image_size(path):
    """解析图片文件头，返回 (格式, 宽, 高)；无法解析返回 ("", 0, 0)。"""
    try:
        with open(path, "rb") as f:
            head = f.read(262144)
            if head[:2] == b"\xff\xd8":
                w, h = _jpeg_dims(f)
                fmt = "JPEG"
            else:
                fmt, w, h = _head_dims(head)
    except (OSError, struct.error):
        return ("", 0, 0)
    if w <= 0 or h <= 0:
        return ("", 0, 0)
    return (fmt, w, h)


def parse_ext_arg(text):
    if not text or not text.strip():
        return set(DEFAULT_EXTS)
    items = [t.strip().lower() for t in text.split(",") if t.strip()]
    if "*" in items or "all" in items:
        return None
    out = set()
    for t in items:
        out.add(t if t.startswith(".") else "." + t)
    return out or set(DEFAULT_EXTS)


def collect_files(root, recursive, exts):
    if recursive:
        found = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for name in filenames:
                found.append(os.path.join(dirpath, name))
    else:
        try:
            found = [os.path.join(root, n) for n in os.listdir(root)]
        except OSError as exc:
            print("错误: 无法读取目录 %s: %s" % (root, exc), file=sys.stderr)
            raise SystemExit(2)
    found.sort(key=str.lower)
    if exts is None:
        return [p for p in found if os.path.isfile(p)]
    return [p for p in found
            if os.path.isfile(p) and os.path.splitext(p)[1].lower() in exts]


def ensure_dir(path):
    if not os.path.isdir(path):
        print("错误: 目录不存在: %s" % path, file=sys.stderr)
        raise SystemExit(2)


def force_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def build_parser():
    p = argparse.ArgumentParser(
        prog="img-filter-ratio",
        description="按宽高比 (ratio = 宽/高) 区间筛选目录中的图片。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python img-filter-ratio.py D:/pics --portrait\n"
               "  python img-filter-ratio.py D:/pics --landscape 1.2\n"
               "  python img-filter-ratio.py D:/pics --min 0.9 --max 1.1 -r\n")
    p.add_argument("directory", nargs="?", default=".",
                   help="要扫描的目录 (默认: 当前目录)")
    p.add_argument("--min", dest="min_ratio", type=float, metavar="R",
                   help="宽高比下限 (含)")
    p.add_argument("--max", dest="max_ratio", type=float, metavar="R",
                   help="宽高比上限 (含)")
    p.add_argument("--portrait", nargs="?", const=1.0, default=None, type=float,
                   metavar="R", help="竖版: ratio < 1; 可加阈值, 如 --portrait 0.8")
    p.add_argument("--landscape", nargs="?", const=1.0, default=None, type=float,
                   metavar="R", help="横版: ratio > 1; 可加阈值, 如 --landscape 1.2")
    p.add_argument("--square", action="store_true",
                   help="方形: |ratio - 1| <= --tol")
    p.add_argument("--tol", type=float, default=0.01, metavar="T",
                   help="方形判定容差 (默认: 0.01)")
    p.add_argument("-r", "--recursive", action="store_true",
                   help="递归扫描子目录")
    p.add_argument("--ext", default="", metavar="LIST",
                   help="扩展名列表 (逗号分隔; '*' 表示所有文件)")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="列出无法解析的文件")
    return p


def main(argv=None):
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    ensure_dir(args.directory)

    conds = []
    if args.min_ratio is not None:
        conds.append(("ratio >= %g" % args.min_ratio,
                      lambda r, a=args.min_ratio: r >= a))
    if args.max_ratio is not None:
        conds.append(("ratio <= %g" % args.max_ratio,
                      lambda r, a=args.max_ratio: r <= a))
    if args.portrait is not None:
        conds.append(("ratio < %g" % args.portrait,
                      lambda r, a=args.portrait: r < a))
    if args.landscape is not None:
        conds.append(("ratio > %g" % args.landscape,
                      lambda r, a=args.landscape: r > a))
    if args.square:
        conds.append(("|ratio - 1| <= %g" % args.tol,
                      lambda r, a=args.tol: abs(r - 1.0) <= a))
    if not conds:
        print("错误: 至少需要一个筛选条件 "
              "(--min/--max/--portrait/--landscape/--square)。", file=sys.stderr)
        return 2

    exts = parse_ext_arg(args.ext)
    files = collect_files(args.directory, args.recursive, exts)
    matches, unreadable = [], []
    for path in files:
        fmt, w, h = read_image_size(path)
        if w <= 0 or h <= 0:
            unreadable.append(path)
            continue
        ratio = w / h
        if all(fn(ratio) for _, fn in conds):
            matches.append((path, fmt, w, h, ratio))

    print("扫描目录: %s%s" % (args.directory, " (递归)" if args.recursive else ""))
    print("筛选条件: %s" % " 且 ".join(label for label, _ in conds))
    print("图片文件: %d (命中 %d, 无法解析 %d)"
          % (len(files), len(matches), len(unreadable)))
    if args.verbose and unreadable:
        for p in unreadable:
            print("  [无法解析] %s" % p)
    print("-" * 64)
    if not matches:
        print("  (无匹配图片)")
        return 0
    matches.sort(key=lambda t: (t[4], t[0].lower()))
    for path, fmt, w, h, ratio in matches:
        if abs(ratio - 1.0) <= args.tol:
            tag = "方"
        elif ratio < 1:
            tag = "竖"
        else:
            tag = "横"
        print("  %6.3f  %dx%-6d %-4s %s  %s" % (ratio, w, h, fmt, tag, path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
