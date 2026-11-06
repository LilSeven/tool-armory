#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""exif-datetime-set —— 等长字节替换修改 EXIF 日期时间字段

用途:
    修改 EXIF 的 DateTime 系字段, 只做"等长字节替换":
      - IFD0    DateTime           (0x0132, "YYYY:MM:DD HH:MM:SS\\0", 20 字节)
      - ExifIFD DateTimeOriginal  (0x9003, 同上)
      - ExifIFD DateTimeDigitized(0x9004, 同上)
      - GPSIFD  GPSDateStamp       (0x001D, "YYYY:MM:DD\\0", 11 字节)
    新旧值长度相同, 因此不移动任何数据、不改动任何 IFD/缩略图偏移,
    文件其余字节保持原样 (仅目标字段的字节被覆盖, 文件长度不变)。
    支持 JPEG (APP1 "Exif\\0\\0") 与 TIFF 两种容器。仅依赖 Python 标准库。

示例命令:
    python exif-datetime-set.py photo.jpg --value "2024:06:01 12:34:56"
    python exif-datetime-set.py photo.jpg --value "2024:06:01" --keep-time
    python exif-datetime-set.py photo.jpg --value "2024:06:01" --tags original,gps
    python exif-datetime-set.py in.jpg -o out.jpg --value "2024:01:02 03:04:05"
    python exif-datetime-set.py photo.jpg --show

退出码: 0 成功; 1 无 EXIF/无目标字段/写入失败; 2 参数或取值错误。
"""

import argparse
import re
import struct
import sys
from pathlib import Path

EXIF_SIG = b"Exif\x00\x00"

TAG_INFO = {
    0x0132: ("datetime", "DateTime (IFD0)"),
    0x9003: ("original", "DateTimeOriginal (Exif IFD)"),
    0x9004: ("digitized", "DateTimeDigitized (Exif IFD)"),
    0x001D: ("gps", "GPSDateStamp (GPS IFD)"),
}
SUB_IFD = {0x8769: "ExifIFD", 0x8825: "GPSIFD"}

RE_FULL = re.compile(r"^(\d{4}:\d{2}:\d{2}) (\d{2}:\d{2}:\d{2})$")
RE_DATE = re.compile(r"^(\d{4}:\d{2}:\d{2})$")
RE_TIME = re.compile(r"^\d{2}:\d{2}:\d{2}$")


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


def collect_targets(data, t0, wanted):
    """收集目标字段的绝对文件偏移与旧值。"""
    cur = TiffCursor(data, t0)
    targets = []
    for label, erel, tag, typ, cnt in cur.iter_entries():
        info = TAG_INFO.get(tag)
        if not info or tag not in wanted:
            continue
        name = info[1]
        if typ != 2:
            print("warning: {} in {} has type {} (expected 2=ASCII); skipped".format(name, label, typ), file=sys.stderr)
            continue
        if cnt <= 4:
            print("warning: {} in {} has odd count {}; skipped".format(name, label, cnt), file=sys.stderr)
            continue
        try:
            vabs = cur.abs_(cur.u32(erel + 8))
        except struct.error:
            continue
        if vabs + cnt > len(data):
            print("warning: {} value at 0x{:X} runs past end of file; skipped".format(name, vabs), file=sys.stderr)
            continue
        targets.append({"tag": tag, "label": label, "name": name,
                        "count": cnt, "abs": vabs, "old": data[vabs:vabs + cnt]})
    return targets


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="exif-datetime-set",
        description="Rewrite EXIF DateTime-family fields via equal-length in-place byte replacement.",
    )
    ap.add_argument("file", help="JPEG (with APP1 Exif) or TIFF file")
    ap.add_argument("--value", help='"YYYY:MM:DD HH:MM:SS" or "YYYY:MM:DD"')
    ap.add_argument("--keep-time", action="store_true",
                    help="with a date-only --value, keep each field's original time of day")
    ap.add_argument("--tags", default="datetime,original,digitized,gps",
                    help="comma list from: datetime,original,digitized,gps (default: all)")
    ap.add_argument("--show", action="store_true", help="only show current values, change nothing")
    ap.add_argument("-o", "--output", help="write result to a new file instead of modifying in place")
    args = ap.parse_args(argv)

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

    wanted = set()
    for token in args.tags.split(","):
        key = token.strip().lower()
        tags = [t for t, (k, _n) in TAG_INFO.items() if k == key]
        if not tags:
            print("error: unknown tag name {!r}; use one of: {}".format(
                token, ", ".join(k for k, _n in TAG_INFO.values())), file=sys.stderr)
            return 2
        wanted.add(tags[0])

    targets = collect_targets(data, t0, wanted)

    if args.show:
        if not targets:
            print("no DateTime-family fields found", file=sys.stderr)
            return 1
        for t in targets:
            text = t["old"].decode("ascii", "replace").rstrip("\x00")
            print("{:<8}  {:<30} @0x{:08X}  \"{}\" (count={})".format(
                t["label"], t["name"], t["abs"], text, t["count"]))
        return 0

    if not args.value:
        print("error: --value is required to modify (or use --show)", file=sys.stderr)
        return 2
    if not (RE_FULL.match(args.value) or RE_DATE.match(args.value)):
        print('error: --value must look like "YYYY:MM:DD HH:MM:SS" or "YYYY:MM:DD"', file=sys.stderr)
        return 2

    m = RE_FULL.match(args.value)
    if m:
        date, time = m.group(1), m.group(2)
    else:
        date, time = RE_DATE.match(args.value).group(1), None

    patches = []
    for t in targets:
        is_gps = t["tag"] == 0x001D
        ok_len = (10, 11) if is_gps else (19, 20)
        if t["count"] not in ok_len:
            print("warning: {} has non-standard count {}; skipped".format(t["name"], t["count"]), file=sys.stderr)
            continue
        tval = time
        if tval is None:
            tval = "00:00:00"
            if args.keep_time and len(t["old"]) >= 19:
                tail = t["old"][11:19].decode("ascii", "replace")
                if RE_TIME.match(tail):
                    tval = tail
        if is_gps:
            new = date.encode("ascii") + (b"\x00" if t["count"] == 11 else b"")
        else:
            new = "{} {}".format(date, tval).encode("ascii") + (b"\x00" if t["count"] == 20 else b"")
        if len(new) != t["count"]:
            print("internal error: new length {} != {} for {}".format(len(new), t["count"], t["name"]), file=sys.stderr)
            return 1
        old_text = t["old"].decode("ascii", "replace").rstrip("\x00")
        if not is_gps and not RE_FULL.match(old_text):
            print("warning: old value {!r} in {} does not look like a timestamp; replacing anyway (equal length)".format(old_text, t["name"]), file=sys.stderr)
        patches.append((t, new, old_text))

    if not patches:
        print("error: no field with a standard length could be patched", file=sys.stderr)
        return 1

    for t, new, old_text in patches:
        new_text = new.rstrip(b"\x00").decode("ascii")
        print("{:<8}  {:<30} @0x{:08X}  \"{}\" -> \"{}\"".format(t["label"], t["name"], t["abs"], old_text, new_text))
    try:
        if args.output:
            buf = bytearray(data)
            for t, new, _old in patches:
                buf[t["abs"]:t["abs"] + len(new)] = new
            Path(args.output).write_bytes(bytes(buf))
        else:
            with open(path, "r+b") as fh:
                for t, new, _old in patches:
                    fh.seek(t["abs"])
                    fh.write(new)
    except OSError as exc:
        print("error: write failed: {}".format(exc), file=sys.stderr)
        return 1
    print("{} field(s) updated by equal-length byte replacement; file length unchanged ({} bytes).".format(
        len(patches), len(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
