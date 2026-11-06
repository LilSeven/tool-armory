#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EXIF 一致性检查 — 核对 EXIF 记录的宽高/DPI 与真实文件头是否一致，标出后期处理过的矛盾。

对每张图片做头部级解析（不解码像素）：
  真实值:  JPEG 取 SOF 宽高、JFIF(APP0) 密度; PNG 取 IHDR 宽高、pHYs 密度
  EXIF 值: JPEG APP1(Exif) / PNG eXIf 里的 PixelXDimension(0xA002)、
           PixelYDimension(0xA003)、XResolution(0x011A) + ResolutionUnit(0x0128)
逐项对比宽、高、DPI，不一致即点名输出——这类矛盾通常意味着文件经过裁剪/缩放
等后期处理，而 EXIF 元数据没有同步更新。

用法:
    python exif-consistency.py photo.jpg edited.png
    python exif-consistency.py ./screenshots
    python exif-consistency.py ./pics --json
    # 中文输出乱码时: python -X utf8 exif-consistency.py ./pics

状态: OK=一致, MISMATCH=矛盾(疑似后期处理), NO-EXIF=无 EXIF 可比, ERROR=解析失败。
退出码恒为 0（不一致是发现而非错误）。只读，不修改任何文件。仅用标准库。
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


# ---------------- JPEG ----------------
def jpeg_segments(data):
    """SOI 之后、SOS 之前的全部 (marker, payload); 非 JPEG 返回 None。"""
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


def jpeg_info(data):
    segs = jpeg_segments(data)
    if segs is None:
        return None
    info = {"fmt": "JPEG", "width": None, "height": None,
            "dpi": None, "exif_tiff": None}
    for m, p in segs:
        if m in SOF_MARKERS and len(p) >= 5:
            info["height"], info["width"] = struct.unpack_from(">HH", p, 1)
        elif m == 0xE0 and p[:5] == b"JFIF\x00" and len(p) >= 9:
            units = p[7]
            (xd,) = struct.unpack_from(">H", p, 8)
            if units == 1:
                info["dpi"] = float(xd)
            elif units == 2:
                info["dpi"] = xd * 2.54
        elif m == 0xE1 and p[:6] == b"Exif\x00\x00" and info["exif_tiff"] is None:
            info["exif_tiff"] = p[6:]
    return info


# ---------------- TIFF / EXIF ----------------
def parse_tiff(data):
    """解析 TIFF 的 IFD0（含链式 IFD）与 Exif 子 IFD(0x8769)，返回 {tag: (typ, vals)}; 异常返回 {}。"""
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


def _exif_dims(tags):
    w = h = 0
    v = tags.get(0xA002, (None, None))[1]
    if v:
        w = v[0]
    v = tags.get(0xA003, (None, None))[1]
    if v:
        h = v[0]
    return (w or None), (h or None)


def _exif_dpi(tags):
    """返回 (dpi, 单位说明); 无法给出物理 DPI 时 dpi=None。"""
    xr = tags.get(0x011A, (None, None))[1]
    if not xr:
        return None, None
    num, den = xr[0]
    if not den:
        return None, None
    unit_v = tags.get(0x0128, (None, None))[1]
    unit = unit_v[0] if unit_v else 2      # EXIF 默认 ResolutionUnit=2(英寸)
    if unit == 2:
        return num / den, "英寸"
    if unit == 3:
        return num / den * 2.54, "厘米"
    return None, "无单位"


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


def png_info(data):
    chunks = png_chunks(data)
    if chunks is None:
        return None
    info = {"fmt": "PNG", "width": None, "height": None,
            "dpi": None, "exif_tiff": None}
    for typ, p in chunks:
        if typ == b"IHDR" and len(p) >= 8:
            info["width"], info["height"] = struct.unpack_from(">II", p)
        elif typ == b"pHYs" and len(p) >= 9:
            px, _py, unit = struct.unpack_from(">IIB", p)
            if unit == 1:
                info["dpi"] = round(px * 0.0254, 1)
        elif typ == b"eXIf" and info["exif_tiff"] is None:
            info["exif_tiff"] = p
    return info


# ---------------- 对比 ----------------
def analyze(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        return {"file": path, "status": "ERROR", "error": str(e)}
    if data[:2] == b"\xff\xd8":
        info = jpeg_info(data)
    elif data[:8] == PNG_SIG:
        info = png_info(data)
    else:
        return {"file": path, "status": "ERROR", "error": "不是 JPEG/PNG"}
    if info is None or info["width"] is None:
        return {"file": path, "status": "ERROR", "error": "无法解析文件头"}

    tags = parse_tiff(info["exif_tiff"]) if info["exif_tiff"] else {}
    ex_w, ex_h = _exif_dims(tags) if tags else (None, None)
    ex_dpi, ex_unit = _exif_dpi(tags) if tags else (None, None)

    diffs = []
    if ex_w and ex_w != info["width"]:
        diffs.append("宽 EXIF=%d ≠ 真实=%d" % (ex_w, info["width"]))
    if ex_h and ex_h != info["height"]:
        diffs.append("高 EXIF=%d ≠ 真实=%d" % (ex_h, info["height"]))
    if ex_dpi is not None and info["dpi"] is not None and abs(ex_dpi - info["dpi"]) > 0.5:
        diffs.append("DPI EXIF=%.0f ≠ 真实=%.0f" % (ex_dpi, info["dpi"]))

    if not (ex_w or ex_h or ex_dpi is not None):
        status = "NO-EXIF"
    elif diffs:
        status = "MISMATCH"
    else:
        status = "OK"
    return {
        "file": path, "status": status, "fmt": info["fmt"],
        "real": {"w": info["width"], "h": info["height"],
                 "dpi": round(info["dpi"], 1) if info["dpi"] is not None else None},
        "exif": {"w": ex_w, "h": ex_h, "unit": ex_unit,
                 "dpi": round(ex_dpi, 1) if ex_dpi is not None else None},
        "diffs": diffs,
    }


def _fp(v):
    return "-" if v is None else "%.0f" % v


def print_report(rows):
    for r in rows:
        if r["status"] == "ERROR":
            print("[ERROR   ] %s — %s" % (r["file"], r.get("error", "?")))
            continue
        real, ex = r["real"], r["exif"]
        dpi_str = _fp(ex["dpi"]) + ("/%s" % ex["unit"] if ex["unit"] and ex["dpi"] is not None else "")
        print("[%-8s] %s  %s  真实 %sx%s @%s | EXIF %sx%s @%s" % (
            r["status"], r["file"], r["fmt"],
            real["w"], real["h"], _fp(real["dpi"]),
            ex["w"] if ex["w"] else "-", ex["h"] if ex["h"] else "-", dpi_str))
        if r["diffs"]:
            print("           └─ %s  ← 疑似后期处理，EXIF 未同步" % "; ".join(r["diffs"]))
        elif r["status"] == "NO-EXIF":
            print("           └─ 头部可读，但没有 EXIF 宽高/DPI 可核对")
    n = {"OK": 0, "MISMATCH": 0, "NO-EXIF": 0, "ERROR": 0}
    for r in rows:
        n[r["status"]] = n.get(r["status"], 0) + 1
    print("-" * 72)
    print("共 %d 个文件: 一致 %d, 不一致 %d, 无EXIF可比 %d, 错误 %d"
          % (len(rows), n["OK"], n["MISMATCH"], n["NO-EXIF"], n["ERROR"]))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="EXIF 一致性检查: EXIF 记录的宽高/DPI vs 真实文件头")
    ap.add_argument("paths", nargs="+", help="图片文件或目录（目录仅查 jpg/jpeg/png）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args(argv)
    _setup_stdio()
    rows = [analyze(p) for p in collect_paths(args.paths)]
    if not rows:
        print("没有找到可检查的图片文件。")
        return 0
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print_report(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
