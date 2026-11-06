#!/usr/bin/env python3
"""camera-tally —— 按 EXIF 厂商（Make）与机型（Model）统计照片数量。

扫描给定的图片文件或目录，读取 EXIF 的 Make/Model 标签，统计每个机身
各拍了多少张，按张数降序输出。只用 Python 标准库，不依赖 Pillow。

用法:
    python camera-tally.py <文件或目录>... [-r]

示例命令:
    python camera-tally.py D:/photos              # 统计目录（仅一层）
    python camera-tally.py D:/photos -r           # 递归统计子目录
    python camera-tally.py IMG_0001.jpg IMG_0002.jpg

说明:
    * 只有 JPEG / TIFF 能解析出 EXIF；PNG/GIF/BMP/WebP 或没有 EXIF
      的文件统一计入 "(无 EXIF)"。
"""

import argparse
import os
import struct
import sys
from collections import Counter

IMG_EXTS = {".jpg", ".jpeg", ".tif", ".tiff", ".png", ".gif", ".bmp", ".webp"}

# ---------------------------------------------------------------------------
# 极简 EXIF 解析（仅标准库，覆盖本工具用到的标签）
# ---------------------------------------------------------------------------

_TIFF_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1,
               7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}


def _tiff_value(typ, num, raw, endian):
    """按 TIFF 字段类型解码原始字节。"""
    if typ == 2:  # ASCII
        return raw.split(b"\x00", 1)[0].decode("ascii", "replace").strip()
    try:
        if typ in (1, 6, 7):
            return raw
        if typ == 3:
            return list(struct.unpack(endian + "%dH" % num, raw))
        if typ == 8:
            return list(struct.unpack(endian + "%dh" % num, raw))
        if typ == 4:
            return list(struct.unpack(endian + "%dI" % num, raw))
        if typ == 9:
            return list(struct.unpack(endian + "%di" % num, raw))
        if typ == 5:
            vals = struct.unpack(endian + "%dI" % (2 * num), raw)
            return [vals[i] / vals[i + 1] if vals[i + 1] else None
                    for i in range(0, len(vals), 2)]
        if typ == 10:
            vals = struct.unpack(endian + "%di" % (2 * num), raw)
            return [vals[i] / vals[i + 1] if vals[i + 1] else None
                    for i in range(0, len(vals), 2)]
    except struct.error:
        return None
    return raw


def _tiff_parse(blob):
    """解析 TIFF 结构（JPEG 的 Exif APP1 内容，或 TIFF 文件本体）。"""
    if len(blob) < 8:
        return {}
    endian = {b"II": "<", b"MM": ">"}.get(blob[:2])
    if endian is None:
        return {}

    def unpack(fmt, off):
        return struct.unpack_from(endian + fmt, blob, off)

    try:
        ifd0 = unpack("I", 4)[0]
    except struct.error:
        return {}

    tags = {}
    visited = set()

    def read_ifd(off):
        if off in visited or off < 8 or off + 2 > len(blob):
            return
        visited.add(off)
        try:
            count = unpack("H", off)[0]
        except struct.error:
            return
        for _ in range(count):
            p = off + 2 + 12 * _
            if p + 12 > len(blob):
                return
            tag, typ, num = unpack("HHI", p)
            size = _TIFF_SIZES.get(typ, 1) * num
            if size <= 4:
                raw = blob[p + 8:p + 8 + size]
            else:
                try:
                    voff = unpack("I", p + 8)[0]
                except struct.error:
                    return
                if voff >= len(blob):
                    tags[tag] = None
                    continue
                raw = blob[voff:voff + size]
            tags[tag] = _tiff_value(typ, num, raw, endian)
        try:
            nxt = unpack("I", off + 2 + 12 * count)[0]
        except struct.error:
            return
        if nxt:
            read_ifd(nxt)

    read_ifd(ifd0)
    sub = tags.get(0x8769)  # ExifIFDPointer
    if isinstance(sub, list) and sub and isinstance(sub[0], int):
        read_ifd(sub[0])
    return tags


def jpeg_exif(data):
    """从 JPEG 字节流中提取 EXIF 标签字典；没有返回 {}。"""
    if data[:2] != b"\xff\xd8":
        return {}
    n = len(data)
    i = 2
    while i + 4 <= n:
        if data[i] != 0xFF:
            return {}
        marker = data[i + 1]
        if marker == 0xFF:  # 连续填充字节
            i += 1
            continue
        if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker in (0xD9, 0xDA):  # EOI/SOS 之后不会再有 EXIF
            break
        seg_len = struct.unpack_from(">H", data, i + 2)[0]
        if seg_len < 2:
            return {}
        if marker == 0xE1 and data[i + 4:i + 10] == b"Exif\x00\x00":
            return _tiff_parse(data[i + 10:i + 2 + seg_len])
        i += 2 + seg_len
    return {}


def read_exif(path, limit=4 * 1024 * 1024):
    """读取文件的 EXIF（JPEG APP1 或 TIFF 本体），无则返回 {}。"""
    try:
        with open(path, "rb") as f:
            head = f.read(limit)
    except OSError:
        return {}
    if head[:2] == b"\xff\xd8":
        return jpeg_exif(head)
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return _tiff_parse(head)
    return {}


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------

TAG_MAKE = 0x010F
TAG_MODEL = 0x0110


def iter_images(paths, recursive=False):
    """按常见图片扩展名收集文件路径。"""
    for p in paths:
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            if recursive:
                for root, dirs, files in os.walk(p):
                    dirs.sort()
                    for name in sorted(files):
                        if os.path.splitext(name)[1].lower() in IMG_EXTS:
                            yield os.path.join(root, name)
            else:
                try:
                    names = sorted(os.listdir(p))
                except OSError as exc:
                    print("[警告] 无法列出目录 %s: %s" % (p, exc), file=sys.stderr)
                    continue
                for name in names:
                    fp = os.path.join(p, name)
                    if os.path.isfile(fp) and os.path.splitext(name)[1].lower() in IMG_EXTS:
                        yield fp
        else:
            print("[警告] 路径不存在: %s" % p, file=sys.stderr)


def _safe_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _safe_stdio()
    parser = argparse.ArgumentParser(
        prog="camera-tally",
        description="按 EXIF 厂商与机型统计照片数量（纯标准库解析 EXIF）。",
    )
    parser.add_argument("paths", nargs="+", help="图片文件或目录")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="递归扫描子目录")
    args = parser.parse_args(argv)

    tally = Counter()
    total = 0
    for fp in iter_images(args.paths, args.recursive):
        total += 1
        tags = read_exif(fp)
        if tags:
            make = tags.get(TAG_MAKE) or "未知厂商"
            model = tags.get(TAG_MODEL) or "未知机型"
            key = f"{make} {model}".strip()
        else:
            key = "(无 EXIF)"
        tally[key] += 1

    if total == 0:
        print("未找到图片文件。")
        return 0
    print(f"共扫描 {total} 张图片，按厂商/机型统计（张数  占比  机型）：")
    for key, cnt in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {cnt:>5}  {cnt * 100.0 / total:5.1f}%  {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
