#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""img-info-all.py —— 单图全景信息（仅用 Python 标准库）。

一条命令汇总单张图片的格式、尺寸、位深、色彩模式、DPI、元数据，
并做基础健康检查（签名 / 截断 / CRC / 尾部垃圾数据等）。
支持 PNG / JPEG / GIF / BMP / WebP / TIFF，按文件头魔数识别而非扩展名。

示例命令：
    python img-info-all.py IMAGE.png
    python img-info-all.py photo.jpg
    python img-info-all.py scan.tif

退出码：0=健康检查全部通过（允许 info）；1=有失败项（损坏/截断/无法识别）。
"""

import argparse
import os
import struct
import sys
import time
import zlib

PNG_SIG = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
COLOR_NAMES = {0: "Grayscale", 2: "Truecolor RGB", 3: "Indexed (palette)",
               4: "Grayscale+Alpha", 6: "Truecolor+Alpha (RGBA)"}
VALID_BD = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
TIFF_TYPES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}
TIFF_COMP = {1: "none", 2: "CCITT RLE", 5: "LZW", 6: "JPEG (old)", 7: "JPEG",
             8: "Adobe Deflate", 32773: "PackBits"}
TIFF_PHOTO = {0: "WhiteIsZero", 1: "BlackIsZero", 2: "RGB", 3: "Palette"}
BMP_COMP = {0: "BI_RGB", 1: "BI_RLE8", 2: "BI_RLE4", 3: "BI_BITFIELDS",
            6: "BI_ALPHABITFIELDS"}


def human(n):
    x = float(n)
    for i, unit in enumerate(("B", "KiB", "MiB", "GiB", "TiB")):
        if x < 1024 or i == 4:
            return ("%d %s" % (round(x), unit)) if i == 0 else ("%.1f %s" % (x, unit))
        x /= 1024.0
    return "%d B" % n


def blank(fmt_name, detail=None):
    return {"format": fmt_name, "format_detail": detail, "width": None,
            "height": None, "depth_desc": None, "color_desc": None, "dpi": None,
            "dpi_src": None, "frames": None, "meta": [], "health": []}


# ---------------------------------------------------------------- PNG ----

def walk_chunks(data):
    """宽容版 PNG 块遍历：返回 (chunks, trailing, err)，尽量收集到 IEND 为止。"""
    chunks = []
    pos = 8
    n = len(data)
    err = None
    while pos < n:
        if pos + 8 > n:
            err = "file truncated in chunk header at offset %d" % pos
            break
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        if pos + 12 + length > n:
            err = ("chunk %r truncated (file ends early)"
                   % ctype.decode("latin-1", "replace"))
            break
        payload = data[pos + 8:pos + 8 + length]
        stored = struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])[0]
        ok = (zlib.crc32(ctype + payload) & 0xFFFFFFFF) == stored
        chunks.append((ctype, payload, ok))
        pos += 12 + length
        if ctype == b"IEND":
            break
    if err is None and (not chunks or chunks[-1][0] != b"IEND"):
        err = "no IEND chunk found (file truncated?)"
    trailing = (n - pos) if (chunks and chunks[-1][0] == b"IEND") else 0
    return chunks, trailing, err


def png_text_meta(chunks, meta):
    for t, p, _ in chunks:
        if t == b"tEXt":
            k, _, v = p.partition(b"\x00")
            meta.append("tEXt %s = %r" % (k.decode("latin-1", "replace"),
                                          v.decode("latin-1", "replace")))
        elif t == b"zTXt":
            k, _, rest = p.partition(b"\x00")
            try:
                v = zlib.decompress(rest[1:]).decode("latin-1", "replace")
                meta.append("zTXt %s = %r" % (k.decode("latin-1", "replace"), v))
            except Exception:
                meta.append("zTXt %s = <decompress failed>" % k.decode("latin-1", "replace"))
        elif t == b"iTXt":
            k, _, rest = p.partition(b"\x00")
            try:
                cf = rest[0]
                body = rest[2:]
                lang, _, rest3 = body.partition(b"\x00")
                _trans, _, text = rest3.partition(b"\x00")
                if cf == 1:
                    text = zlib.decompress(text)
                meta.append("iTXt %s[%s] = %r" % (k.decode("latin-1", "replace"),
                                                  lang.decode("latin-1", "replace"),
                                                  text.decode("utf-8", "replace")))
            except Exception:
                meta.append("iTXt %s = <parse failed>" % k.decode("latin-1", "replace"))
        elif t == b"tIME":
            try:
                y, mo, d, hh, mm, ss = struct.unpack(">HBBBBB", p)
                meta.append("tIME %04d-%02d-%02d %02d:%02d:%02d (UTC)" % (y, mo, d, hh, mm, ss))
            except Exception:
                meta.append("tIME <bad payload>")
        elif t == b"eXIf":
            meta.append("eXIf chunk (%d B)" % len(p))


def analyze_png(data):
    info = blank("PNG")
    h = info["health"]
    h.append(("OK", "PNG signature"))
    chunks, trailing, err = walk_chunks(data)
    if err:
        h.append(("FAIL", err))
    if not chunks:
        return info
    types = [t for t, _, _ in chunks]
    if types[0] != b"IHDR":
        h.append(("FAIL", "first chunk is %r, not IHDR"
                  % types[0].decode("latin-1", "replace")))
    bad = [t.decode("latin-1", "replace") for t, _, ok in chunks if not ok]
    if bad:
        h.append(("FAIL", "chunk CRC mismatch: %s" % ", ".join(bad)))
    else:
        h.append(("OK", "all %d chunk CRCs valid" % len(chunks)))
    ihdr = next((p for t, p, _ in chunks if t == b"IHDR"), None)
    if ihdr and len(ihdr) == 13:
        w, hh, bd, ct, comp, filt, il = struct.unpack(">IIBBBBB", ihdr)
        info["width"], info["height"] = w, hh
        info["depth_desc"] = "%d bits/channel" % bd
        info["color_desc"] = COLOR_NAMES.get(ct, "color type %d" % ct)
        probs = []
        if w == 0 or hh == 0:
            probs.append("zero dimension")
        if comp != 0:
            probs.append("compression method %d != 0" % comp)
        if filt != 0:
            probs.append("filter method %d != 0" % filt)
        if il not in (0, 1):
            probs.append("interlace %d not in {0,1}" % il)
        if bd not in VALID_BD.get(ct, ()):
            probs.append("bit depth %d invalid for color type %d" % (bd, ct))
        if ct == 3 and b"PLTE" not in types:
            probs.append("color type 3 requires PLTE")
        if probs:
            h.append(("FAIL", "IHDR: " + "; ".join(probs)))
        else:
            h.append(("OK", "IHDR fields valid (%dx%d, %s, depth %d, interlace %d)"
                      % (w, hh, info["color_desc"], bd, il)))
    elif ihdr:
        h.append(("FAIL", "IHDR payload is %d bytes (want 13)" % len(ihdr)))
    idat = b"".join(p for t, p, _ in chunks if t == b"IDAT")
    if not idat:
        h.append(("FAIL", "no IDAT (no image data)"))
    else:
        try:
            dobj = zlib.decompressobj()
            raw = dobj.decompress(idat)
            try:
                raw += dobj.flush()
            except Exception:
                pass
            extra = len(dobj.unused_data)
            if extra:
                h.append(("WARN", "IDAT zlib stream has %d trailing byte(s)" % extra))
            else:
                h.append(("OK", "IDAT zlib stream decodes (%s raw)" % human(len(raw))))
        except zlib.error as e:
            h.append(("FAIL", "IDAT zlib error: %s" % e))
    if b"IEND" in types:
        if trailing:
            h.append(("WARN", "%d trailing byte(s) after IEND" % trailing))
        elif not err:
            h.append(("OK", "IEND is the last chunk, no trailing data"))
    else:
        h.append(("FAIL", "no IEND chunk"))
    if b"PLTE" in types and b"IDAT" in types and types.index(b"PLTE") > types.index(b"IDAT"):
        h.append(("FAIL", "PLTE appears after the first IDAT"))
    phys = next((p for t, p, _ in chunks if t == b"pHYs"), None)
    if phys and len(phys) == 9:
        ppu_x, ppu_y, unit = struct.unpack(">IIB", phys)
        if unit == 1:
            info["dpi"] = (round(ppu_x * 0.0254, 1), round(ppu_y * 0.0254, 1))
            info["dpi_src"] = "pHYs (pixels per metre)"
        else:
            info["meta"].append("pHYs aspect ratio %d:%d (unit=0, no absolute DPI)"
                                % (ppu_x, ppu_y))
    actl = next((p for t, p, _ in chunks if t == b"acTL"), None)
    if actl and len(actl) >= 4:
        nf = struct.unpack(">I", actl[:4])[0]
        info["frames"] = nf
        info["format_detail"] = "APNG (%d frames)" % nf
    else:
        info["frames"] = 1
    png_text_meta(chunks, info["meta"])
    return info


# --------------------------------------------------------------- JPEG ----

def tiff_val(en, typ, cnt, raw):
    if typ == 2:
        return raw.split(b"\x00")[0].decode("latin-1", "replace")
    need = TIFF_TYPES.get(typ, 1) * cnt
    if len(raw) < need:
        return None
    if typ in (1, 6, 7):
        return raw if cnt > 1 else raw[0]
    if typ == 3:
        vals = struct.unpack(en + "%dH" % cnt, raw)
    elif typ == 4:
        vals = struct.unpack(en + "%dI" % cnt, raw)
    elif typ == 8:
        vals = struct.unpack(en + "%dh" % cnt, raw)
    elif typ == 9:
        vals = struct.unpack(en + "%di" % cnt, raw)
    elif typ == 5:
        v = struct.unpack(en + "%dI" % (2 * cnt), raw)
        vals = tuple((v[2 * i], v[2 * i + 1]) for i in range(cnt))
    elif typ == 10:
        v = struct.unpack(en + "%di" % (2 * cnt), raw)
        vals = tuple((v[2 * i], v[2 * i + 1]) for i in range(cnt))
    elif typ == 11:
        vals = struct.unpack(en + "%df" % cnt, raw)
    elif typ == 12:
        vals = struct.unpack(en + "%dd" % cnt, raw)
    else:
        return raw
    return vals[0] if cnt == 1 else list(vals)


def read_ifd(data, off, en):
    """解析一个 TIFF IFD。返回 (tags dict, next_ifd_offset, oob_count)。"""
    if off < 0 or off + 2 > len(data):
        raise ValueError("IFD offset %d out of range" % off)
    cnt = struct.unpack(en + "H", data[off:off + 2])[0]
    tags = {}
    oob = 0
    p = off + 2
    for _ in range(cnt):
        if p + 12 > len(data):
            oob += 1
            break
        tag, typ = struct.unpack(en + "HH", data[p:p + 4])
        c2 = struct.unpack(en + "I", data[p + 4:p + 8])[0]
        size = TIFF_TYPES.get(typ, 1) * c2
        if size <= 4:
            raw = data[p + 8:p + 8 + size]
        else:
            vo = struct.unpack(en + "I", data[p + 8:p + 12])[0]
            if vo + size > len(data):
                oob += 1
                raw = b""
            else:
                raw = data[vo:vo + size]
        try:
            v = tiff_val(en, typ, c2, raw)
        except Exception:
            v = None
            oob += 1
        if tag not in tags:
            tags[tag] = v
        p += 12
    nxt = struct.unpack(en + "I", data[p:p + 4])[0] if p + 4 <= len(data) else 0
    return tags, nxt, oob


def parse_exif(blob):
    """blob 为 TIFF 头开始的 EXIF 数据。返回 (tags, ifd1_offset)。"""
    tags = {}
    nxt = 0
    if len(blob) < 8:
        return tags, nxt
    if blob[:2] == b"II":
        en = "<"
    elif blob[:2] == b"MM":
        en = ">"
    else:
        return tags, nxt
    try:
        if struct.unpack(en + "H", blob[2:4])[0] != 42:
            return tags, nxt
        off = struct.unpack(en + "I", blob[4:8])[0]
        tags, nxt, _ = read_ifd(blob, off, en)
    except Exception:
        pass
    return tags, nxt


SOF_NAMES = {0xC0: "baseline (SOF0)", 0xC1: "extended sequential (SOF1)",
             0xC2: "progressive (SOF2)", 0xC3: "lossless (SOF3)"}
SOF_SET = (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF)


def analyze_jpeg(data):
    info = blank("JPEG")
    h = info["health"]
    h.append(("OK", "SOI marker"))
    n = len(data)
    pos = 2
    sof = None
    sof_marker = None
    jfif = None
    exif_tags = {}
    exif_thumb = False
    xmp_sz = 0
    coms = []
    other_app = []
    embedded_soi = []
    eoi_pos = None
    sos_count = 0
    while pos < n:
        if data[pos] != 0xFF:
            h.append(("FAIL", "lost marker sync at offset %d (0x%02X)" % (pos, data[pos])))
            return info
        while pos < n and data[pos] == 0xFF:
            pos += 1
        if pos >= n:
            break
        m = data[pos]
        pos += 1
        if m == 0xD8:
            embedded_soi.append(pos)
            continue
        if m == 0xD9:
            eoi_pos = pos
            break
        if m == 0x01 or 0xD0 <= m <= 0xD7:
            continue
        if pos + 2 > n:
            h.append(("FAIL", "truncated segment header at offset %d" % pos))
            return info
        seglen = struct.unpack(">H", data[pos:pos + 2])[0]
        if seglen < 2 or pos + seglen > n:
            h.append(("FAIL", "bad segment length %d at offset %d" % (seglen, pos)))
            return info
        payload = data[pos + 2:pos + seglen]
        if m == 0xDA:
            sos_count += 1
            pos += seglen
            while pos + 1 < n:
                if data[pos] != 0xFF:
                    pos += 1
                    continue
                b1 = data[pos + 1]
                if b1 == 0x00 or 0xD0 <= b1 <= 0xD7:
                    pos += 2
                    continue
                if b1 == 0xFF:
                    pos += 1
                    continue
                break
            if pos + 1 >= n:
                break
            continue
        if m in SOF_SET and sof is None:
            sof_marker = m
            if len(payload) >= 6:
                prec, hh, ww, nc = struct.unpack(">BHHB", payload[:6])
                sof = (prec, hh, ww, nc)
        elif m == 0xE0 and payload[:5] == b"JFIF\x00" and len(payload) >= 12:
            jfif = struct.unpack(">BHH", payload[7:12])
        elif m == 0xE1 and payload[:6] == b"Exif\x00\x00":
            exif_tags, nxt_ifd = parse_exif(payload[6:])
            exif_thumb = nxt_ifd != 0
        elif m == 0xE1 and payload.startswith(b"http://ns.adobe.com/xap/1.0/\x00"):
            xmp_sz = len(payload) - 29
        elif m == 0xFE:
            coms.append(payload.decode("latin-1", "replace"))
        elif 0xE0 <= m <= 0xEF:
            other_app.append("APP%d" % (m - 0xE0))
        pos += seglen
    if eoi_pos is None:
        h.append(("FAIL", "no EOI marker found (file truncated?)"))
    else:
        h.append(("OK", "EOI marker present"))
        if n - eoi_pos > 0:
            h.append(("WARN", "%d trailing byte(s) after EOI" % (n - eoi_pos)))
    if sof:
        prec, hh, ww, nc = sof
        info["width"], info["height"] = ww, hh
        info["depth_desc"] = "%d-bit precision" % prec
        cmap = {1: "Grayscale", 3: "YCbCr", 4: "CMYK"}
        info["color_desc"] = cmap.get(nc, "%d components" % nc)
        h.append(("OK", "SOF parsed (%dx%d, %d component(s))" % (ww, hh, nc)))
    else:
        h.append(("FAIL", "no SOF frame header (dimensions unknown)"))
    if sos_count:
        h.append(("OK", "%d entropy-coded scan(s) skipped" % sos_count))
    else:
        h.append(("FAIL", "no SOS (no image data)"))
    if embedded_soi:
        h.append(("INFO", "%d embedded SOI marker(s) (likely embedded thumbnails)"
                  % len(embedded_soi)))
    if sof_marker:
        info["format_detail"] = SOF_NAMES.get(sof_marker, "SOF 0x%02X" % sof_marker)
    if exif_thumb:
        info["meta"].append("EXIF thumbnail (IFD1) present")
    if other_app:
        info["meta"].append("segments: %s" % ", ".join(other_app))
    if xmp_sz:
        info["meta"].append("XMP packet (%d B)" % xmp_sz)
    for c in coms:
        info["meta"].append("COM comment: %r" % c)
    for tag, name in ((271, "Make"), (272, "Model"), (305, "Software"),
                      (306, "DateTime"), (315, "Artist"), (274, "Orientation"),
                      (33432, "Copyright")):
        if exif_tags.get(tag):
            info["meta"].append("EXIF %s = %r" % (name, exif_tags[tag]))
    # DPI：JFIF 与 EXIF 候选
    cands = []
    if jfif:
        units, xd, yd = jfif
        if units == 1 and xd and yd:
            cands.append((xd, yd, "JFIF density (dpi)"))
        elif units == 2 and xd and yd:
            cands.append((round(xd * 2.54, 1), round(yd * 2.54, 1), "JFIF density (dpcm)"))
    xr, yr = exif_tags.get(282), exif_tags.get(283)
    ru = exif_tags.get(296, 2)
    if isinstance(xr, tuple) and isinstance(yr, tuple) and xr[1] and yr[1]:
        fx, fy = xr[0] / xr[1], yr[0] / yr[1]
        if ru == 2:
            cands.append((round(fx, 1), round(fy, 1), "EXIF XResolution (inch)"))
        elif ru == 3:
            cands.append((round(fx * 2.54, 1), round(fy * 2.54, 1), "EXIF XResolution (cm)"))
    if cands:
        info["dpi"] = (cands[0][0], cands[0][1])
        info["dpi_src"] = cands[0][2]
        if len(cands) > 1 and abs(cands[0][0] - cands[1][0]) > 0.5:
            h.append(("WARN", "DPI sources disagree: %s vs %s"
                      % (cands[0], cands[1])))
    info["frames"] = sos_count or None
    return info


# ---------------------------------------------------------------- GIF ----

def analyze_gif(data):
    info = blank("GIF")
    h = info["health"]
    n = len(data)
    info["format_detail"] = data[:6].decode("ascii")
    h.append(("OK", "GIF signature (%s)" % info["format_detail"]))
    w, hh = struct.unpack("<HH", data[6:10])
    flags = data[10]
    info["width"], info["height"] = w, hh
    pos = 13
    gct_n = 0
    if flags & 0x80:
        gct_n = 2 << (flags & 0x07)
        pos += 3 * gct_n
    info["depth_desc"] = "%d-bit palette indices" % ((flags & 0x07) + 1)
    info["color_desc"] = ("global color table, %d entries" % gct_n) if gct_n \
        else "no global color table"
    frames = 0
    delays = []
    comments = []
    apps = []
    interlaced = 0
    trailer = False
    while pos < n:
        b = data[pos]
        if b == 0x3B:
            trailer = True
            pos += 1
            break
        if b == 0x21:
            if pos + 2 > n:
                h.append(("FAIL", "truncated extension at offset %d" % pos))
                return info
            label = data[pos + 1]
            pos += 2
            blocks = b""
            truncated_ext = False
            while pos < n:
                sz = data[pos]
                pos += 1
                if sz == 0:
                    break
                if pos + sz > n:
                    truncated_ext = True
                    break
                blocks += data[pos:pos + sz]
                pos += sz
            if truncated_ext:
                h.append(("FAIL", "truncated extension block at offset %d" % pos))
                return info
            if label == 0xFE:
                comments.append(blocks.decode("latin-1", "replace"))
            elif label == 0xF9 and len(blocks) >= 3:
                delays.append(struct.unpack("<H", blocks[1:3])[0])
            elif label == 0xFF and len(blocks) >= 11:
                apps.append(blocks[:11].rstrip(b"\x00").decode("latin-1", "replace"))
            continue
        if b == 0x2C:
            if pos + 10 > n:
                h.append(("FAIL", "truncated image descriptor at offset %d" % pos))
                return info
            lflags = data[pos + 9]
            pos += 10
            if lflags & 0x80:
                pos += 3 * (2 << (lflags & 0x07))
            if lflags & 0x40:
                interlaced += 1
            if pos >= n:
                h.append(("FAIL", "file ends inside image block"))
                return info
            pos += 1  # LZW min code size
            while pos < n:
                sz = data[pos]
                pos += 1
                if sz == 0:
                    break
                pos += sz
            frames += 1
            continue
        h.append(("FAIL", "unexpected block 0x%02X at offset %d" % (b, pos)))
        return info
    if not trailer:
        h.append(("FAIL", "no trailer (0x3B) found (file truncated?)"))
    else:
        h.append(("OK", "trailer found"))
        if pos < n:
            h.append(("WARN", "%d trailing byte(s) after trailer" % (n - pos)))
        else:
            h.append(("OK", "no trailing data after trailer"))
    if not frames:
        h.append(("FAIL", "no image data (0 frames)"))
    else:
        h.append(("OK", "%d frame(s) parsed" % frames))
    info["frames"] = frames
    if frames > 1 or apps:
        loop = None
        if "NETSCAPE2.0" in apps:
            info["meta"].append("application extension: NETSCAPE2.0 (animated loop)")
    if delays:
        info["meta"].append("frame delays: %s (1/100 s each)"
                            % ", ".join(str(d) for d in delays))
    for c in comments:
        info["meta"].append("comment: %r" % c)
    if interlaced:
        info["meta"].append("%d interlaced frame(s)" % interlaced)
    return info


# ---------------------------------------------------------------- BMP ----

def analyze_bmp(data):
    info = blank("BMP")
    h = info["health"]
    n = len(data)
    bfsize = struct.unpack("<I", data[2:6])[0]
    off = struct.unpack("<I", data[10:14])[0]
    hdr = struct.unpack("<I", data[14:18])[0]
    h.append(("OK", "BMP signature ('BM')"))
    if hdr == 12:
        w = struct.unpack("<h", data[18:20])[0]
        hh = struct.unpack("<h", data[20:22])[0]
        bpp = struct.unpack("<H", data[24:26])[0]
        comp = 0
        xppm = yppm = 0
        h.append(("OK", "BITMAPCOREHEADER (12 B)"))
    elif hdr >= 40:
        w, hh = struct.unpack("<ii", data[18:26])
        bpp = struct.unpack("<H", data[28:30])[0]
        comp = struct.unpack("<I", data[30:34])[0]
        if n >= 46:
            xppm, yppm = struct.unpack("<ii", data[38:46])
        else:
            xppm = yppm = 0
        h.append(("OK", "DIB header size %d B" % hdr))
    else:
        h.append(("FAIL", "unsupported DIB header size %d" % hdr))
        return info
    info["width"], info["height"] = w, abs(hh)
    info["depth_desc"] = "%d bits/pixel" % bpp
    info["color_desc"] = BMP_COMP.get(comp, "compression %d" % comp)
    if hh < 0:
        h.append(("INFO", "negative height: rows stored top-down"))
    if bfsize == 0:
        h.append(("INFO", "bfSize field is 0 (some writers leave it blank)"))
    elif bfsize != n:
        h.append(("WARN", "bfSize says %d B but file is %d B" % (bfsize, n)))
    else:
        h.append(("OK", "bfSize matches file size"))
    if off >= 14 + hdr:
        h.append(("OK", "pixel data offset %d is beyond headers" % off))
    else:
        h.append(("FAIL", "pixel data offset %d overlaps headers" % off))
    if bpp not in (1, 4, 8, 16, 24, 32):
        h.append(("WARN", "unusual bit count %d" % bpp))
    if comp == 0 and bpp == 24:
        row = ((w * 3 + 3) // 4) * 4
        need = row * abs(hh)
        avail = n - off
        if avail < need:
            h.append(("WARN", "pixel area short: need ~%d B, only %d B after offset"
                      % (need, avail)))
        else:
            h.append(("OK", "pixel area size plausible (%d B available)" % avail))
    if xppm > 0 and yppm > 0:
        info["dpi"] = (round(xppm * 0.0254, 1), round(yppm * 0.0254, 1))
        info["dpi_src"] = "biXPelsPerMeter/biYPelsPerMeter"
    return info


# --------------------------------------------------------------- WebP ----

def analyze_webp(data):
    info = blank("WebP")
    h = info["health"]
    n = len(data)
    riff = struct.unpack("<I", data[4:8])[0]
    if riff + 8 != n:
        h.append(("WARN", "RIFF size field says %d B but file is %d B (%s)"
                  % (riff + 8, n, "truncated" if riff + 8 < n else "trailing data")))
    else:
        h.append(("OK", "RIFF size matches file size"))
    pos = 12
    names = []
    vpx = v8 = vpl = None
    anim_frames = 0
    exif_sz = xmp_sz = 0
    truncated = False
    while pos + 8 <= n:
        fourcc = data[pos:pos + 4]
        sz = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        payload = data[pos + 8:pos + 8 + sz]
        name = fourcc.decode("latin-1", "replace")
        names.append(name)
        if len(payload) < sz:
            h.append(("FAIL", "chunk %s truncated (want %d B)" % (name, sz)))
            truncated = True
            break
        if fourcc == b"VP8X":
            vpx = payload
        elif fourcc == b"VP8 ":
            v8 = payload
        elif fourcc == b"VP8L":
            vpl = payload
        elif fourcc == b"ANMF":
            anim_frames += 1
        elif fourcc == b"EXIF":
            exif_sz = sz
        elif fourcc == b"XMP ":
            xmp_sz = sz
        pos += 8 + sz + (sz & 1)
    if not truncated and pos != n:
        h.append(("WARN", "%d unparsed trailing byte(s) after chunk list" % (n - pos)))
    if not names:
        h.append(("FAIL", "no WebP chunks found"))
        return info
    h.append(("OK", "chunks: %s" % ", ".join(names)))
    if vpx is not None and len(vpx) >= 10:
        flags = vpx[0]
        cw = int.from_bytes(vpx[4:7], "little") + 1
        ch = int.from_bytes(vpx[7:10], "little") + 1
        info["width"], info["height"] = cw, ch
        parts = []
        if flags & 0x02:
            parts.append("animation")
        if flags & 0x10:
            parts.append("alpha")
        if flags & 0x20:
            parts.append("ICC")
        info["format_detail"] = "extended (" + (", ".join(parts) or "simple") + ")"
        info["depth_desc"] = "8 bits/channel (VP8/VP8L)"
        if flags & 0x08 and not exif_sz:
            h.append(("WARN", "VP8X declares EXIF but no EXIF chunk found"))
    elif v8 is not None and len(v8) >= 10 and v8[3:6] == b"\x9d\x01\x2a":
        w = struct.unpack("<H", v8[6:8])[0] & 0x3FFF
        hh = struct.unpack("<H", v8[8:10])[0] & 0x3FFF
        info["width"], info["height"] = w, hh
        info["format_detail"] = "lossy (VP8)"
        info["depth_desc"] = "8 bits/channel (YUV420)"
    elif vpl is not None and len(vpl) >= 5 and vpl[0] == 0x2F:
        bits = struct.unpack("<I", vpl[1:5])[0]
        w = (bits & 0x3FFF) + 1
        hh = ((bits >> 14) & 0x3FFF) + 1
        info["width"], info["height"] = w, hh
        info["format_detail"] = "lossless (VP8L)"
        info["depth_desc"] = "8 bits/channel" + (" + alpha" if (bits >> 28) & 1 else "")
    else:
        h.append(("FAIL", "no usable VP8/VP8L/VP8X payload (dimensions unknown)"))
        return info
    h.append(("OK", "dimensions decoded from %s" %
              ("VP8X" if vpx is not None else "VP8 " if v8 is not None else "VP8L")))
    info["frames"] = anim_frames or 1
    if exif_sz:
        info["meta"].append("EXIF chunk (%d B)" % exif_sz)
    if xmp_sz:
        info["meta"].append("XMP chunk (%d B)" % xmp_sz)
    return info


# --------------------------------------------------------------- TIFF ----

def analyze_tiff(data):
    info = blank("TIFF")
    h = info["health"]
    n = len(data)
    if data[:2] == b"II":
        en = "<"
        detail = "little-endian (II)"
    else:
        en = ">"
        detail = "big-endian (MM)"
    info["format_detail"] = detail
    magic = struct.unpack(en + "H", data[2:4])[0]
    if magic != 42:
        h.append(("FAIL", "bad TIFF magic %d (want 42)" % magic))
        return info
    h.append(("OK", "TIFF header (%s, magic 42)" % detail))
    off = struct.unpack(en + "I", data[4:8])[0]
    if off + 2 > n:
        h.append(("FAIL", "IFD0 offset %d out of range" % off))
        return info
    try:
        tags, nxt, oob = read_ifd(data, off, en)
    except (struct.error, ValueError) as e:
        h.append(("FAIL", "IFD0 unreadable: %s" % e))
        return info
    h.append(("OK", "IFD0 parsed (%d tags)" % len(tags)))
    if oob:
        h.append(("WARN", "%d IFD0 entry(ies) unreadable/out of range" % oob))
    else:
        h.append(("OK", "all IFD0 value offsets within file"))
    w, hh = tags.get(256), tags.get(257)
    info["width"], info["height"] = w, hh
    if w and hh:
        h.append(("OK", "dimensions %dx%d" % (w, hh)))
    else:
        h.append(("WARN", "missing ImageWidth/ImageLength tags"))
    bits = tags.get(258)
    if bits is not None:
        if isinstance(bits, int):
            bits = [bits]
        info["depth_desc"] = "%s bits/sample" % "/".join(str(b) for b in bits)
    comp = tags.get(259)
    photo = tags.get(262)
    info["color_desc"] = "%s, compression %s" % (
        TIFF_PHOTO.get(photo, "photometric %s" % photo),
        TIFF_COMP.get(comp, "id %s" % comp))
    pages = 1
    seen = {off}
    cur = nxt
    while cur and len(seen) < 32:
        if cur in seen or cur + 2 > n:
            break
        seen.add(cur)
        try:
            _, cur2, _ = read_ifd(data, cur, en)
        except Exception:
            h.append(("WARN", "IFD at offset %d unreadable" % cur))
            break
        pages += 1
        cur = cur2
    info["frames"] = pages
    xr, yr = tags.get(282), tags.get(283)
    ru = tags.get(296)
    if isinstance(xr, tuple) and xr[1]:
        fx = xr[0] / xr[1]
        fy = yr[0] / yr[1] if isinstance(yr, tuple) and yr[1] else fx
        if ru == 2:
            info["dpi"] = (round(fx, 1), round(fy, 1))
            info["dpi_src"] = "XResolution (inch)"
        elif ru == 3:
            info["dpi"] = (round(fx * 2.54, 1), round(fy * 2.54, 1))
            info["dpi_src"] = "XResolution (cm)"
        else:
            info["meta"].append("resolution %s/%s (unit=%s, no absolute DPI)"
                                % (xr, yr, ru))
    names = {270: "Description", 271: "Make", 272: "Model", 305: "Software",
             306: "DateTime", 315: "Artist", 33432: "Copyright"}
    for tag, name in sorted(names.items()):
        if tags.get(tag):
            info["meta"].append("TIFF %s = %r" % (name, tags[tag]))
    return info


# ------------------------------------------------------------- driver ----

def analyze_file(path):
    with open(path, "rb") as f:
        data = f.read()
    st = os.stat(path)
    if data.startswith(PNG_SIG):
        r = analyze_png(data)
    elif data[:3] == b"\xff\xd8\xff":
        r = analyze_jpeg(data)
    elif data[:6] in (b"GIF87a", b"GIF89a"):
        r = analyze_gif(data)
    elif data[:2] == b"BM" and len(data) >= 26:
        r = analyze_bmp(data)
    elif data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
        r = analyze_webp(data)
    elif data[:4] in (b"II*\x00", b"MM\x00*"):
        r = analyze_tiff(data)
    else:
        r = blank("unknown")
        r["health"].append(("FAIL", "unrecognized image signature"))
    r["path"] = path
    r["filesize"] = len(data)
    r["mtime"] = st.st_mtime
    return r


def print_report(info):
    lines = []
    lines.append("== Image all-in-one info ==")
    lines.append("File       : %s (%s, modified %s)"
                 % (info["path"], human(info["filesize"]),
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(info["mtime"]))))
    fmt = info["format"]
    if info["format_detail"]:
        fmt += " (%s)" % info["format_detail"]
    lines.append("Format     : " + fmt)
    if info["width"] is not None:
        lines.append("Dimensions : %d x %d" % (info["width"], info["height"]))
    else:
        lines.append("Dimensions : unknown")
    lines.append("Bit depth  : %s" % (info["depth_desc"] or "n/a"))
    lines.append("Color mode : %s" % (info["color_desc"] or "n/a"))
    if info["dpi"]:
        lines.append("DPI        : %g x %g  (from %s)"
                     % (info["dpi"][0], info["dpi"][1], info["dpi_src"]))
    else:
        lines.append("DPI        : N/A")
    if info["frames"] is not None:
        lines.append("Frames     : %s" % info["frames"])
    if info["meta"]:
        lines.append("Metadata   :")
        for m in info["meta"]:
            lines.append("  - " + m)
    else:
        lines.append("Metadata   : (none)")
    counts = {"OK": 0, "INFO": 0, "WARN": 0, "FAIL": 0}
    lines.append("Health checks:")
    for lvl, msg in info["health"]:
        counts[lvl] = counts.get(lvl, 0) + 1
        lines.append("  [%s] %s" % (lvl.ljust(4), msg))
    verdict = "FAIL" if counts["FAIL"] else "PASS"
    lines.append("Result: %s -- %d ok, %d info, %d warning(s), %d failure(s)"
                 % (verdict, counts["OK"], counts["INFO"], counts["WARN"], counts["FAIL"]))
    return "\n".join(lines), verdict


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        prog="img-info-all",
        description="Summarize one image: format, dimensions, bit depth, DPI, "
                    "metadata and basic health checks (PNG/JPEG/GIF/BMP/WebP/TIFF).")
    ap.add_argument("image", help="image file to inspect")
    args = ap.parse_args(argv)
    try:
        info = analyze_file(args.image)
    except OSError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    text, verdict = print_report(info)
    print(text)
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
