#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可剥离元数据报告 — 统计每张图片含多少可剥离的元数据字节（EXIF/XMP/注释），输出隐私清理收益预估。

JPEG: 统计 APP1(Exif)、APP1(XMP)、COM(注释) 三类段的完整字节数——剥离即整段
删除, 文件等量变小; ICC 色彩档案(APP2) 与 APP13(Photoshop/IPTC) 单列为"其他"。
PNG: 统计 eXIf 与 tEXt/iTXt/zTXt 文本块（其中 iTXt+XML:com.adobe.xmp 计入
XMP）——这些辅助块删除后 PNG 依然有效。

用法:
    python img-exif-strip-report.py ./photos
    python img-exif-strip-report.py a.jpg b.png --json
    # 中文乱码时: python -X utf8 img-exif-strip-report.py ./photos

退出码恒为 0。只读，不修改任何文件。仅用标准库。
"""

import argparse
import json
import os
import struct
import sys

IMG_EXTS = {".jpg", ".jpeg", ".png"}
SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
               0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
PNG_SIG = b"\x89PNG\r\n\x1a\n"
XMP_SIG = b"http://ns.adobe.com/xap/1.0/\x00"


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


# ---------------- JPEG ----------------
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


def jpeg_meta(data):
    segs = jpeg_segments(data)
    if segs is None:
        return None
    res = {"fmt": "JPEG", "exif": 0, "xmp": 0, "comment": 0, "other": 0}
    for m, p in segs:
        total = 4 + len(p)          # FF + marker + 2字节长度域 + payload
        if m == 0xE1 and p[:6] == b"Exif\x00\x00":
            res["exif"] += total
        elif m == 0xE1 and p.startswith(XMP_SIG):
            res["xmp"] += total
        elif m == 0xFE:
            res["comment"] += total
        elif (m == 0xE2 and p[:11] == b"ICC_PROFILE") or m == 0xED:
            res["other"] += total
    return res


# ---------------- PNG ----------------
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


def png_meta(data):
    chunks = png_chunks(data)
    if chunks is None:
        return None
    res = {"fmt": "PNG", "exif": 0, "xmp": 0, "comment": 0, "other": 0}
    for typ, p in chunks:
        total = 12 + len(p)         # 4字节长度域 + 4字节类型 + 数据 + 4字节CRC
        if typ == b"eXIf":
            res["exif"] += total
        elif typ == b"iTXt" and p.startswith(b"XML:com.adobe.xmp\x00"):
            res["xmp"] += total
        elif typ in (b"tEXt", b"iTXt", b"zTXt"):
            res["comment"] += total
    return res


# ---------------- 汇总 ----------------
def analyze(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        return {"file": path, "status": "ERROR", "error": str(e)}
    if data[:2] == b"\xff\xd8":
        meta = jpeg_meta(data)
    elif data[:8] == PNG_SIG:
        meta = png_meta(data)
    else:
        return {"file": path, "status": "ERROR", "error": "不是 JPEG/PNG"}
    if meta is None:
        return {"file": path, "status": "ERROR", "error": "文件头不完整"}
    strip = meta["exif"] + meta["xmp"] + meta["comment"]
    size = len(data)
    return {"file": path, "status": "OK", "fmt": meta["fmt"], "size": size,
            "exif": meta["exif"], "xmp": meta["xmp"], "comment": meta["comment"],
            "other": meta["other"], "strippable": strip,
            "pct": round(strip / size * 100, 1) if size else 0.0,
            "after": size - strip}


def print_report(rows):
    print("%-46s %10s %8s %7s %7s %10s %7s" % (
        "文件", "文件大小", "EXIF", "XMP", "注释", "可剥离", "占比"))
    print("-" * 100)
    t_size = t_strip = t_other = n_ok = 0
    for r in rows:
        if r["status"] == "ERROR":
            print("%-46s  错误: %s" % (r["file"], r.get("error", "")))
            continue
        print("%-46s %10s %8s %7s %7s %10s %6.1f%%" % (
            r["file"], format(r["size"], ","),
            format(r["exif"], ","), format(r["xmp"], ","), format(r["comment"], ","),
            format(r["strippable"], ","), r["pct"]))
        t_size += r["size"]
        t_strip += r["strippable"]
        t_other += r["other"]
        n_ok += 1
    print("-" * 100)
    pct = t_strip / t_size * 100 if t_size else 0.0
    print("合计 %d 个有效文件 | 总大小 %s B | 可剥离 %s B (占 %.1f%%) | 清理后预计共省 %s B"
          % (n_ok, format(t_size, ","), format(t_strip, ","), pct, format(t_strip, ",")))
    if t_other:
        print("另有 ICC/Photoshop 等其他元数据 %s B 未计入上表（剥离可能影响色彩显示），明细见 --json"
              % format(t_other, ","))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="可剥离元数据报告: 每张图的 EXIF/XMP/注释字节数与隐私清理收益")
    ap.add_argument("paths", nargs="+", help="图片文件或目录（目录仅查 jpg/jpeg/png）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args(argv)
    _setup_stdio()
    rows = [analyze(p) for p in collect_paths(args.paths)]
    if not rows:
        print("没有找到可分析的图片文件。")
        return 0
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print_report(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
