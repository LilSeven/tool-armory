#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""exif-orientation-fix —— 最小侵入修正 EXIF Orientation 方向标志

用途:
    改写 EXIF IFD0 中的 Orientation (0x0112) 字节, 使方向标志与实际像素方向一致。
    Orientation 是 IFD 项里的内联 SHORT (count=1), 整个修改只覆盖文件中的
    2 个字节, 不移动/重写任何其他数据, 文件长度不变。
    默认动作 --reset 即设为 1 (正常直立, 即像素按存储方向观看);
    也可 --set N (1..8) 显式指定, 使标志与真实拍摄方向一致。
    附带读取实际像素尺寸, 提示当前/新标志下查看器将看到的宽高。
    支持 JPEG (APP1 "Exif\\0\\0") 与 TIFF。仅依赖 Python 标准库。

示例命令:
    python exif-orientation-fix.py photo.jpg --show
    python exif-orientation-fix.py photo.jpg --reset
    python exif-orientation-fix.py in.jpg --set 6 -o out.jpg

退出码: 0 成功(含无需修改); 1 无 EXIF/无 Orientation/无法设置; 2 参数错误。
"""

import argparse
import struct
import sys
from pathlib import Path

EXIF_SIG = b"Exif\x00\x00"
SUB_IFD = {0x8769: "ExifIFD", 0x8825: "GPSIFD"}
SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
               0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}

ORIENTATION_NAMES = {
    1: "Horizontal (normal)",
    2: "Mirror horizontal",
    3: "Rotate 180",
    4: "Mirror vertical",
    5: "Mirror horizontal and rotate 270 CW",
    6: "Rotate 90 CW",
    7: "Mirror horizontal and rotate 90 CW",
    8: "Rotate 270 CW",
}


class ToolError(Exception):
    """可预期的解析错误: 输出干净信息, 退出码 1。"""


class TiffCursor:
    """在 data[tiff_off:] 上按 TIFF 相对偏移读取, 自动处理 II/MM 字节序。"""

    def __init__(self, data, tiff_off):
        self.data = data
        self.t0 = tiff_off
        endian = data[tiff_off:tiff_off + 2]
        if endian == b"II":
            self.e = "<"
        elif endian == b"MM":
            self.e = ">"
        else:
            raise ToolError("not a TIFF stream (missing II/MM byte-order mark)")
        magic, first = struct.unpack_from(self.e + "HI", data, tiff_off + 2)
        if magic != 42:
            raise ToolError("bad TIFF magic {} (expected 42)".format(magic))
        self.first = first

    def u16(self, rel):
        return struct.unpack_from(self.e + "H", self.data, self.t0 + rel)[0]

    def u32(self, rel):
        return struct.unpack_from(self.e + "I", self.data, self.t0 + rel)[0]

    def abs_(self, rel):
        return self.t0 + rel

    def iter_entries(self):
        """yield (ifd标签, entry相对偏移, tag, type, count); 遍历 IFD0/IFD1/Exif/GPS。"""
        seen = set()
        work = [("IFD0", self.first, True)]
        for label, off, follow_chain in work:
            hops = 0
            while off and off not in seen and hops < 16:
                seen.add(off)
                cur_label = label if hops == 0 else "{}+{}".format(label, hops)
                hops += 1
                try:
                    count = self.u16(off)
                except struct.error:
                    break
                if not (0 < count <= 1024):
                    break
                for i in range(count):
                    erel = off + 2 + 12 * i
                    try:
                        tag = self.u16(erel)
                        typ = self.u16(erel + 2)
                        cnt = self.u32(erel + 4)
                    except struct.error:
                        break
                    yield cur_label, erel, tag, typ, cnt
                    if tag in SUB_IFD and typ == 4 and cnt == 1:
                        try:
                            sub = self.u32(erel + 8)
                        except struct.error:
                            sub = 0
                        if sub:
                            work.append((SUB_IFD[tag], sub, False))
                if not follow_chain:
                    break
                try:
                    off = self.u32(off + 2 + 12 * count)
                except struct.error:
                    break


def find_exif_tiff(data):
    """返回 EXIF 的 TIFF 头绝对偏移; 找不到返回 None。"""
    if data[:2] == b"\xff\xd8":
        n = len(data)
        pos = 2
        while pos + 4 <= n:
            if data[pos] != 0xFF:
                return None
            while pos < n and data[pos] == 0xFF:
                pos += 1
            if pos >= n:
                break
            marker = data[pos]
            pos += 1
            if marker == 0xD8 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
                continue
            if marker in (0xD9, 0xDA):
                break
            if pos + 2 > n:
                break
            seglen = struct.unpack_from(">H", data, pos)[0]
            if seglen < 2:
                break
            payload = data[pos + 2:min(pos + seglen, n)]
            pos += seglen
            if marker == 0xE1 and payload[:6] == EXIF_SIG:
                return pos - seglen + 2 + 6
        return None
    if data[:2] in (b"II", b"MM"):
        return 0
    return None


def jpeg_pixel_size(data):
    """扫描 JPEG 标记流找第一个 SOF, 返回 (宽, 高) 或 None。"""
    n, pos = len(data), 2
    while pos + 4 <= n:
        if data[pos] != 0xFF:
            return None
        while pos < n and data[pos] == 0xFF:
            pos += 1
        if pos >= n:
            return None
        marker = data[pos]
        pos += 1
        if marker == 0xD8 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if marker in (0xD9, 0xDA):
            return None
        if pos + 2 > n:
            return None
        seglen = struct.unpack_from(">H", data, pos)[0]
        if seglen < 2:
            return None
        payload = data[pos + 2:min(pos + seglen, n)]
        pos += seglen
        if marker in SOF_MARKERS and len(payload) >= 5:
            h, w = struct.unpack_from(">HH", payload, 1)
            return w, h
    return None


def tiff_pixel_size(data, t0):
    """从 TIFF IFD0 读 ImageWidth/ImageLength, 返回 (宽, 高) 或 None。"""
    cur = TiffCursor(data, t0)
    w = h = None
    for label, erel, tag, typ, cnt in cur.iter_entries():
        if label != "IFD0" or tag not in (0x0100, 0x0101):
            continue
        if cnt == 1 and typ == 3:
            val = struct.unpack_from(cur.e + "H", data, cur.abs_(erel) + 8)[0]
        elif cnt == 1 and typ == 4:
            val = struct.unpack_from(cur.e + "I", data, cur.abs_(erel) + 8)[0]
        else:
            continue
        if tag == 0x0100:
            w = val
        else:
            h = val
    return (w, h) if w and h else None


def viewer_size(dims, orientation):
    """给定存储尺寸与方向标志, 返回查看器看到的 (宽, 高)。"""
    w, h = dims
    return (h, w) if orientation in (5, 6, 7, 8) else (w, h)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="exif-orientation-fix",
        description="Minimally rewrite the EXIF Orientation byte so the flag matches the real pixel direction.",
    )
    ap.add_argument("file", help="JPEG (with APP1 Exif) or TIFF file")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--set", dest="set_value", type=int, choices=range(1, 9), metavar="N",
                       help="set Orientation to N (1-8)")
    group.add_argument("--reset", action="store_true", help="set Orientation to 1 (normal) [default action]")
    group.add_argument("--show", action="store_true", help="only show current orientation and pixel size")
    ap.add_argument("-o", "--output", help="write result to a new file instead of modifying in place")
    args = ap.parse_args(argv)

    if args.show:
        mode, new = "show", None
    elif args.set_value is not None:
        mode, new = "set", args.set_value
    else:
        mode, new = "reset", 1

    path = Path(args.file)
    try:
        data = path.read_bytes()
    except OSError as exc:
        print("error: cannot read {}: {}".format(path, exc), file=sys.stderr)
        return 1

    t0 = find_exif_tiff(data)
    if t0 is None:
        print('error: no EXIF (APP1 "Exif\\0\\0") found; input must be a JPEG with EXIF or a TIFF', file=sys.stderr)
        return 1
    is_jpeg = data[:2] == b"\xff\xd8"

    cur = TiffCursor(data, t0)
    entry = None
    elsewhere = []
    for label, erel, tag, typ, cnt in cur.iter_entries():
        if tag != 0x0112:
            continue
        if label == "IFD0" and typ == 3 and cnt == 1:
            entry = erel
        else:
            elsewhere.append((label, typ, cnt))

    dims = jpeg_pixel_size(data) if is_jpeg else tiff_pixel_size(data, t0)

    if entry is None:
        note = "no Orientation tag in IFD0 (viewers treat it as 1 = Horizontal (normal))"
        if mode == "set":
            print("error: {}; adding one would shift IFD offsets, refusing non-minimal edit".format(note), file=sys.stderr)
            return 1
        print("note: {}; nothing to fix".format(note))
        return 0

    vabs = cur.abs_(entry) + 8
    old = struct.unpack_from(cur.e + "H", data, vabs)[0]
    old_name = ORIENTATION_NAMES.get(old, "reserved/unknown")

    if mode == "show":
        print("file        : {}".format(path))
        print("container   : {} (TIFF byte order {}, TIFF header @0x{:X})".format(
            "JPEG APP1 Exif" if is_jpeg else "TIFF", "MM" if cur.e == ">" else "II", t0))
        print("orientation : {} ({})".format(old, old_name))
        if elsewhere:
            print("also found  : Orientation entries elsewhere: {}".format(elsewhere))
        if dims:
            vw, vh = viewer_size(dims, old)
            print("pixels      : {} x {}".format(dims[0], dims[1]))
            print("viewer sees : {} x {} with current flag".format(vw, vh))
        return 0

    if old == new:
        print("orientation already {} ({}); no change needed".format(new, ORIENTATION_NAMES[new]))
        return 0

    try:
        if args.output:
            buf = bytearray(data)
            struct.pack_into(cur.e + "H", buf, vabs, new)
            Path(args.output).write_bytes(bytes(buf))
        else:
            with open(path, "r+b") as fh:
                fh.seek(vabs)
                fh.write(struct.pack(cur.e + "H", new))
    except OSError as exc:
        print("error: write failed: {}".format(exc), file=sys.stderr)
        return 1

    print("IFD0 Orientation @0x{:08X}: {} ({}) -> {} ({})".format(
        vabs, old, old_name, new, ORIENTATION_NAMES[new]))
    print("wrote 2 bytes at file offset 0x{:08X}; file length unchanged ({} bytes).".format(vabs, len(data)))
    if dims:
        vw, vh = viewer_size(dims, new)
        print("pixels {} x {}; viewer will see {} x {} with flag {}.".format(dims[0], dims[1], vw, vh, new))
    return 0


if __name__ == "__main__":
    sys.exit(main())
