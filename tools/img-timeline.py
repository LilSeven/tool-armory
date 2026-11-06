#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""照片时间线 — 按 EXIF 拍摄月份统计，并用终端 ASCII 柱状图展示各月数量。

时间来源优先级: EXIF DateTimeOriginal(0x9003) > DateTimeDigitized(0x9004)
> DateTime(0x0132) > 文件修改时间(月号后标 *)。支持 JPEG(APP1 Exif) 与
PNG(eXIf 块)。柱长按各月数量等比缩放（最长 --width 字符）。

用法:
    python img-timeline.py ./photos
    python img-timeline.py ./photos --year 2024 --width 60
    python img-timeline.py ./photos --detail
    python img-timeline.py a.jpg b.png --json
    # 中文乱码时: python -X utf8 img-timeline.py ./photos

退出码恒为 0。只读，不修改任何文件。仅用标准库。
"""

import argparse
import datetime
import json
import os
import re
import struct
import sys

IMG_EXTS = {".jpg", ".jpeg", ".png"}
DT_RE = re.compile(r"^(\d{4})[:-](\d{1,2})[:-](\d{1,2})")
SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
               0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
PNG_SIG = b"\x89PNG\r\n\x1a\n"
_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1,
              8: 2, 9: 4, 10: 8, 11: 4, 12: 8}


def _setup_stdio():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def collect_paths(paths, exts=IMG_EXTS):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                if os.path.splitext(name)[1].lower() in exts:
                    out.append(os.path.join(p, name))
        else:
            out.append(p)
    return out


# ---------------- JPEG / PNG / TIFF 解析 ----------------
def jpeg_segments(data):
    if data[:2] != b"\xff\xd8":
        return None
    segs, i, n = [], 2, len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            break
        m = data[i + 1]
        if m == 0xFF:
            i += 1
            continue
        if m == 0x01 or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        if m == 0xD9:
            break
        (ln,) = struct.unpack_from(">H", data, i + 2)
        if ln < 2:
            break
        segs.append((m, data[i + 4:i + 2 + ln]))
        i += 2 + ln
        if m == 0xDA:
            break
    return segs


def png_chunks(data):
    if data[:8] != PNG_SIG:
        return None
    out, i, n = [], 8, len(data)
    while i + 12 <= n:
        (ln,) = struct.unpack_from(">I", data, i)
        typ = data[i + 4:i + 8]
        if len(typ) < 4:
            break
        out.append((typ, data[i + 8:i + 8 + ln]))
        i += 12 + ln
        if typ == b"IEND":
            break
    return out


def parse_tiff(data):
    """解析 IFD0 与 Exif 子 IFD(0x8769)，返回 {tag: (typ, vals)}; 异常返回 {}。"""
    try:
        if len(data) < 8 or data[:2] not in (b"II", b"MM"):
            return {}
        en = "<" if data[:2] == b"II" else ">"

        def read_ifd(off):
            tags = {}
            if off < 8 or off + 2 > len(data):
                return tags, 0
            (cnt,) = struct.unpack_from(en + "H", data, off)
            for k in range(min(cnt, 512)):
                eo = off + 2 + k * 12
                if eo + 12 > len(data):
                    break
                tag, typ, num = struct.unpack_from(en + "HHI", data, eo)
                size = _TYPE_SIZE.get(typ, 1) * num
                vo = eo + 8 if size <= 4 else struct.unpack_from(en + "I", data, eo + 8)[0]
                vals = None
                if typ == 2 and vo + num <= len(data):
                    vals = data[vo:vo + num].split(b"\x00")[0].decode("ascii", "replace")
                elif typ == 3 and vo + 2 * num <= len(data):
                    vals = list(struct.unpack_from(en + "H" * num, data, vo))
                elif typ in (1, 6, 7) and vo + num <= len(data):
                    vals = list(data[vo:vo + num])
                elif typ in (4, 9) and vo + 4 * num <= len(data):
                    vals = list(struct.unpack_from(en + ("I" if typ == 4 else "i") * num, data, vo))
                elif typ == 5 and vo + 8 * num <= len(data):
                    vals = [struct.unpack_from(en + "II", data, vo + 8 * j)
                            for j in range(num)]
                tags[tag] = (typ, vals)
            nxt = 0
            tail = off + 2 + cnt * 12
            if tail + 4 <= len(data):
                (nxt,) = struct.unpack_from(en + "I", data, tail)
            return tags, nxt

        tags_out = {}
        (off,) = struct.unpack_from(en + "I", data, 4)
        for _ in range(8):
            if not off:
                break
            tags, off = read_ifd(off)
            tags_out.update(tags)
        ptr = tags_out.get(0x8769)
        if ptr and ptr[1]:
            sub, _n = read_ifd(ptr[1][0])
            tags_out.update(sub)
        return tags_out
    except Exception:
        return {}


def exif_datetime(data):
    """返回 (时间字符串, 来源说明) 或 (None, None)。"""
    tiff = None
    if data[:2] == b"\xff\xd8":
        for m, p in jpeg_segments(data) or []:
            if m == 0xE1 and p[:6] == b"Exif\x00\x00":
                tiff = p[6:]
                break
    elif data[:8] == PNG_SIG:
        for typ, p in png_chunks(data) or []:
            if typ == b"eXIf":
                tiff = p
                break
    if not tiff:
        return None, None
    tags = parse_tiff(tiff)
    for tag, label in ((0x9003, "EXIF:DateTimeOriginal"),
                       (0x9004, "EXIF:DateTimeDigitized"),
                       (0x0132, "EXIF:DateTime")):
        v = tags.get(tag, (None, None))[1]
        if isinstance(v, str) and v.strip():
            return v.strip(), label
    return None, None


def month_key(path):
    """返回 (月份键 'YYYY-MM' 或 None, 来源说明, 是否回退自文件时间)。"""
    try:
        with open(path, "rb") as f:
            data = f.read(1 << 22)      # 元数据在头部, 读前 4MB 足够
    except OSError:
        return None, "读取失败", False
    s, label = exif_datetime(data)
    if s:
        m = DT_RE.match(s)
        if m:
            y, mo = int(m.group(1)), int(m.group(2))
            if 1 <= mo <= 12 and 1900 <= y <= 9999:
                return "%04d-%02d" % (y, mo), label, False
    try:
        d = datetime.datetime.fromtimestamp(os.path.getmtime(path))
    except (OSError, ValueError, OverflowError):
        return None, "读取失败", False
    return d.strftime("%Y-%m"), "文件修改时间", True


# ---------------- 展示 ----------------
def print_chart(counts, fallback_set, width):
    keys = sorted(counts)
    if not keys:
        print("没有可统计的时间信息。")
        return
    mx = max(counts.values())
    total = sum(counts.values())
    print("按拍摄月份统计 (共 %d 张, 跨度 %s ~ %s)" % (total, keys[0], keys[-1]))
    print("月份       数量  柱状图 (等比缩放, 最长 %d 字符)" % width)
    for k in keys:
        n = counts[k]
        bar = "#" * max(1, round(n * width / mx))
        print("%s%s %5d  %s" % (k, "*" if k in fallback_set else " ", n, bar))
    peak = max(keys, key=lambda k: counts[k])
    print("-" * 64)
    print("高峰月份: %s (%d 张)" % (peak, counts[peak]))
    if fallback_set:
        print("* = 该月含按文件修改时间估算的照片（无 EXIF 拍摄时间）")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="照片时间线: 按 EXIF 拍摄月份统计 + ASCII 柱状图")
    ap.add_argument("paths", nargs="+", help="图片文件或目录（目录仅查 jpg/jpeg/png）")
    ap.add_argument("--year", type=int, default=None, help="只统计指定年份, 如 2024")
    ap.add_argument("--width", type=int, default=50, help="柱状图最大字符宽 (默认 50)")
    ap.add_argument("--detail", action="store_true", help="逐文件列出月份与时间来源")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args(argv)
    _setup_stdio()
    if args.width < 1:
        ap.error("--width 必须 >= 1")

    counts, fallback_set, detail, skipped = {}, set(), [], []
    for p in collect_paths(args.paths):
        key, src, fb = month_key(p)
        if key is None:
            skipped.append(p)
            continue
        if args.year and not key.startswith("%04d-" % args.year):
            continue
        counts[key] = counts.get(key, 0) + 1
        if fb:
            fallback_set.add(key)
        detail.append({"file": p, "month": key, "source": src})
    if not counts and not skipped:
        print("没有找到可统计的图片文件。")
        return 0
    if args.json:
        print(json.dumps({"months": counts,
                          "fallback_months": sorted(fallback_set),
                          "skipped": skipped, "files": detail},
                         ensure_ascii=False, indent=2))
        return 0
    print_chart(counts, fallback_set, args.width)
    if args.detail:
        print("-" * 64)
        for d in detail:
            print("%s  ->  %s  (%s)" % (d["file"], d["month"], d["source"]))
    if skipped:
        print("(跳过 %d 个无法读取时间的文件)" % len(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
