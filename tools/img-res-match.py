#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分辨率精确匹配 —— 找出与指定分辨率完全一致（或仅差旋转）的所有图片文件。

仅解析图片文件头获取尺寸（不解码像素、不依赖第三方库），支持
PNG / JPEG / GIF / BMP / WebP / TIFF。只用 Python 标准库。

用法:
  python img-res-match.py <目录> (--res WxH | --width W --height H) [--rotate] [-r]

选项:
  --res WxH         目标分辨率, 也接受 1920*1080 / 1920,1080
  --width W         目标宽（与 --height 搭配, 等价于 --res）
  --height H        目标高
  -R, --rotate      同时匹配旋转后的分辨率 (WxH 与 HxW 都算命中)
  -r, --recursive   递归扫描子目录
  --ext LIST        扩展名，逗号分隔（默认 png,jpg,jpeg,gif,bmp,webp,tif,tiff；'*' 表示所有文件）

示例命令:
  python img-res-match.py D:/pics --res 1920x1080
  python img-res-match.py D:/pics --res 1080x1920 --rotate
  python img-res-match.py D:/pics --width 800 --height 600 -r

退出码: 0 正常（含无匹配）；2 参数或目录错误。
"""

import argparse
import os
import re
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
        prog="img-res-match",
        description="找出与指定分辨率完全一致 (或仅差旋转) 的所有图片文件。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python img-res-match.py D:/pics --res 1920x1080\n"
               "  python img-res-match.py D:/pics --res 1080x1920 --rotate\n"
               "  python img-res-match.py D:/pics --width 800 --height 600 -r\n")
    p.add_argument("directory", nargs="?", default=".",
                   help="要扫描的目录 (默认: 当前目录)")
    p.add_argument("--res", metavar="WxH",
                   help="目标分辨率, 如 1920x1080 (也接受 1920*1080 / 1920,1080)")
    p.add_argument("--width", type=int, metavar="W",
                   help="目标宽 (与 --height 搭配)")
    p.add_argument("--height", type=int, metavar="H",
                   help="目标高 (与 --width 搭配)")
    p.add_argument("-R", "--rotate", action="store_true",
                   help="同时匹配旋转后的分辨率 (WxH 与 HxW 都算命中)")
    p.add_argument("-r", "--recursive", action="store_true",
                   help="递归扫描子目录")
    p.add_argument("--ext", default="", metavar="LIST",
                   help="扩展名列表 (逗号分隔; '*' 表示所有文件)")
    return p


def main(argv=None):
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    ensure_dir(args.directory)

    if args.res:
        m = re.match(r"^\s*(\d+)\s*[xX*×,]\s*(\d+)\s*$", args.res)
        if not m:
            print("错误: --res 格式应为 WxH, 例如 1920x1080。", file=sys.stderr)
            return 2
        tw, th = int(m.group(1)), int(m.group(2))
    elif args.width is not None and args.height is not None:
        tw, th = args.width, args.height
    else:
        print("错误: 需要 --res WxH, 或同时指定 --width 与 --height。",
              file=sys.stderr)
        return 2
    if tw <= 0 or th <= 0:
        print("错误: 分辨率必须为正整数。", file=sys.stderr)
        return 2

    targets = {(tw, th)}
    if args.rotate:
        targets.add((th, tw))

    exts = parse_ext_arg(args.ext)
    files = collect_files(args.directory, args.recursive, exts)
    matches = []
    unreadable = 0
    for path in files:
        fmt, w, h = read_image_size(path)
        if w <= 0 or h <= 0:
            unreadable += 1
            continue
        if (w, h) in targets:
            matches.append((path, fmt, w, h))

    extra = ""
    if args.rotate and th != tw:
        extra = " (含旋转: %dx%d)" % (th, tw)
    print("目标分辨率: %dx%d%s" % (tw, th, extra))
    print("扫描目录: %s%s" % (args.directory, " (递归)" if args.recursive else ""))
    print("图片文件: %d (可解析 %d, 无法解析 %d)"
          % (len(files), len(files) - unreadable, unreadable))
    print("匹配结果: %d 个文件" % len(matches))
    if matches:
        print("-" * 64)
        for path, fmt, w, h in matches:
            print("  %dx%d  %-4s  %s" % (w, h, fmt, path))
    else:
        print("  (无匹配文件)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
