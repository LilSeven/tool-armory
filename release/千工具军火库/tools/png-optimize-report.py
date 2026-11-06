#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""png-optimize-report.py —— PNG 优化线索报告（仅用 Python 标准库）。

解析 PNG 的块结构与像素数据，给出可操作的体积优化线索：
真彩色转索引色 / 转灰度 / 去除无用 alpha / 16 位降 8 位 / 剥离辅助块 /
用最高 zlib 级别重压缩 / 滤波器选择 / 交错设置 / IDAT 分块情况等，
并对主要线索给出粗略的体积收益估算。

示例命令：
    python png-optimize-report.py IMAGE.png
    python png-optimize-report.py IMAGE.png --no-pixel    # 只分析块结构，不解码像素

退出码：0=结构分析成功（即使只发现警告）；1=不是有效 PNG 或结构损坏。
"""

import argparse
import os
import struct
import sys
import zlib
from collections import Counter

PNG_SIG = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
COLOR_NAMES = {0: "Grayscale", 2: "Truecolor RGB", 3: "Indexed (palette)",
               4: "Grayscale+Alpha", 6: "Truecolor+Alpha (RGBA)"}
VALID_BD = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
CRITICAL = (b"IHDR", b"PLTE", b"IDAT", b"IEND")
MAX_RAW_WORK = 32 * 1024 * 1024  # 超过此大小的原始像素不再解码分析
SEV = ("HIGH", "MED ", "LOW ", "info")


def human(n):
    x = float(n)
    for i, unit in enumerate(("B", "KiB", "MiB", "GiB", "TiB")):
        if x < 1024 or i == 4:
            return ("%d %s" % (round(x), unit)) if i == 0 else ("%.1f %s" % (x, unit))
        x /= 1024.0
    return "%d B" % n


def read_png(path):
    """返回 (data, chunks, trailing)。chunks 为 (type, payload, crc_ok) 列表；结构损坏抛 ValueError。"""
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(PNG_SIG):
        raise ValueError("not a PNG file (bad signature)")
    chunks = []
    pos = 8
    n = len(data)
    ended = False
    while pos < n:
        if pos + 8 > n:
            raise ValueError("file truncated in chunk header at offset %d" % pos)
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        if pos + 12 + length > n:
            raise ValueError("chunk %r truncated (file ends early)"
                             % ctype.decode("latin-1", "replace"))
        payload = data[pos + 8:pos + 8 + length]
        stored = struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])[0]
        ok = (zlib.crc32(ctype + payload) & 0xFFFFFFFF) == stored
        chunks.append((ctype, payload, ok))
        pos += 12 + length
        if ctype == b"IEND":
            ended = True
            break
    if not ended:
        raise ValueError("no IEND chunk found (file truncated?)")
    return data, chunks, n - pos


def adam7(w, h):
    for x0, y0, dx, dy in ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
                           (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)):
        pw = (w - x0 + dx - 1) // dx
        ph = (h - y0 + dy - 1) // dy
        if pw > 0 and ph > 0:
            yield pw, ph


def unfilter(raw, w, h, bit_depth, color_type, interlace):
    """逆滤波。返回 (lines, leftover)；lines 为 (pass_width, line_bytes, filter_type) 列表。"""
    nch = CHANNELS[color_type]
    bpp_bits = nch * bit_depth
    bpp = max(1, bpp_bits // 8)
    passes = list(adam7(w, h)) if interlace else [(w, h)]
    out = []
    pos = 0
    for pw, ph in passes:
        bpl = (pw * bpp_bits + 7) // 8
        prev = bytes(bpl)
        for _ in range(ph):
            if pos + 1 + bpl > len(raw):
                raise ValueError("image data runs out mid-scanline")
            ft = raw[pos]
            line = bytearray(raw[pos + 1:pos + 1 + bpl])
            pos += 1 + bpl
            if ft == 0:
                pass
            elif ft == 1:
                for i in range(bpp, bpl):
                    line[i] = (line[i] + line[i - bpp]) & 0xFF
            elif ft == 2:
                for i in range(bpl):
                    line[i] = (line[i] + prev[i]) & 0xFF
            elif ft == 3:
                for i in range(bpl):
                    a = line[i - bpp] if i >= bpp else 0
                    line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
            elif ft == 4:
                for i in range(bpl):
                    a = line[i - bpp] if i >= bpp else 0
                    b = prev[i]
                    c = prev[i - bpp] if i >= bpp else 0
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    if pa <= pb and pa <= pc:
                        pr = a
                    elif pb <= pc:
                        pr = b
                    else:
                        pr = c
                    line[i] = (line[i] + pr) & 0xFF
            else:
                raise ValueError("invalid filter type %d" % ft)
            line = bytes(line)
            out.append((pw, line, ft))
            prev = line
    return out, len(raw) - pos


def line_pixels(line, pw, color_type, bit_depth):
    """一行的像素值列表：真彩/灰+alpha 为 bytes 或 tuple；灰度/索引为 int。"""
    nch = CHANNELS[color_type]
    if color_type in (2, 4, 6):
        if bit_depth == 8:
            return [bytes(line[i:i + nch]) for i in range(0, pw * nch, nch)]
        step = 2 * nch
        return [tuple(line[i + 2 * c] for c in range(nch))
                for i in range(0, pw * step, step)]
    if bit_depth == 8:
        return list(line[:pw])
    if bit_depth == 16:
        return list(line[0:2 * pw:2])
    per = 8 // bit_depth
    mask = (1 << bit_depth) - 1
    out = []
    for i in range(pw):
        byte = line[i // per]
        shift = 8 - bit_depth - (i % per) * bit_depth
        out.append((byte >> shift) & mask)
    return out


def pixel_stats(lines, color_type, bit_depth):
    colors = set()
    used = set()
    npx = 0
    all_gray = None
    all_opaque = None
    low_zero = True
    for pw, line, _ft in lines:
        pxs = line_pixels(line, pw, color_type, bit_depth)
        colors.update(pxs)
        used.update(pxs)
        npx += len(pxs)
    if color_type == 2:
        all_gray = True
        for pw, line, _ft in lines:
            if bit_depth == 8:
                r, g, b = line[0:3 * pw:3], line[1:3 * pw:3], line[2:3 * pw:3]
            else:
                r, g, b = line[0:6 * pw:6], line[2:6 * pw:6], line[4:6 * pw:6]
            if r != g or r != b:
                all_gray = False
                break
    elif color_type == 0 and bit_depth == 16:
        for pw, line, _ft in lines:
            if any(lo != 0 for lo in line[1:2 * pw:2]):
                low_zero = False
                break
    if color_type == 6:
        all_opaque = True
        for pw, line, _ft in lines:
            alphas = line[3:4 * pw:4] if bit_depth == 8 else line[7:8 * pw:8]
            if any(a != 0xFF for a in alphas):
                all_opaque = False
                break
    elif color_type == 4:
        all_opaque = True
        for pw, line, _ft in lines:
            alphas = line[1:2 * pw:2] if bit_depth == 8 else line[3:4 * pw:4]
            if any(a != 0xFF for a in alphas):
                all_opaque = False
                break
    if color_type in (2, 6) and bit_depth == 16:
        step = 2 * CHANNELS[color_type]
        for pw, line, _ft in lines:
            if any(line[off:step * pw:step] for off in range(1, step, 2)):
                low_zero = False
                break
    return {"colors": sorted(colors), "n_colors": len(colors), "n_pixels": npx,
            "used": used, "all_gray": all_gray, "all_opaque": all_opaque,
            "low_zero": low_zero}


def pack_bits(values, bits):
    n = len(values)
    bpl = (n * bits + 7) // 8
    buf = bytearray(bpl)
    if bits == 8:
        buf[:n] = bytes(values)
    elif bits == 16:
        for i, v in enumerate(values):
            buf[2 * i] = (v >> 8) & 0xFF
            buf[2 * i + 1] = v & 0xFF
    else:
        per = 8 // bits
        mask = (1 << bits) - 1
        for i, v in enumerate(values):
            buf[i // per] |= (v & mask) << (8 - bits - (i % per) * bits)
    return bytes(buf)


def zlib_len(rows):
    return len(zlib.compress(b"".join(b"\x00" + r for r in rows), 9))


def conversion_candidates(lines, color_type, bit_depth, stats, idat_size):
    """估算“换颜色模式”能省多少字节，返回 [(描述, 省的字节数)]（只保留 >0 的）。"""
    cands = []
    try:
        rows = [line_pixels(l, pw, color_type, bit_depth) for pw, l, _ in lines]
    except Exception:
        return cands
    if color_type in (2, 6) and 0 < stats["n_colors"] <= 256:
        palette = stats["colors"]
        index_of = {px: i for i, px in enumerate(palette)}
        bits = 1
        while bits < 8 and (1 << bits) < len(palette):
            bits *= 2
        packed = [pack_bits([index_of[px] for px in row], bits) for row in rows]
        saving = idat_size - zlib_len(packed) - 3 * len(palette)
        cands.append(("convert to %d-bit indexed (%d colors)" % (bits, len(palette)), saving))
    if color_type == 2 and stats["all_gray"]:
        gray = [pack_bits([px[0] for px in row], 8) for row in rows]
        cands.append(("convert to 8-bit grayscale", idat_size - zlib_len(gray)))
    if color_type == 6 and stats["all_opaque"]:
        rgb = [b"".join(bytes(px[:3]) for px in row) for row in rows]
        cands.append(("drop unused alpha channel", idat_size - zlib_len(rgb)))
    if color_type in (2, 6) and bit_depth == 16 and stats["low_zero"]:
        p8 = [b"".join(bytes(px) for px in row) for row in rows]
        cands.append(("downscale to 8-bit (low bytes all zero, lossless)",
                      idat_size - zlib_len(p8)))
    return [(t, s) for t, s in cands if s > 0]


def analyze(path, do_pixel=True):
    data, chunks, trailing = read_png(path)
    filesize = len(data)
    types = [t for t, _, _ in chunks]
    if types[0] != b"IHDR":
        raise ValueError("first chunk is not IHDR")
    if len(chunks[0][1]) != 13:
        raise ValueError("IHDR payload is %d bytes (want 13)" % len(chunks[0][1]))
    w, h, bd, ct, comp, filt, il = struct.unpack(">IIBBBBB", chunks[0][1])

    issues = []
    if comp != 0:
        issues.append("IHDR compression method=%d (want 0)" % comp)
    if filt != 0:
        issues.append("IHDR filter method=%d (want 0)" % filt)
    if il not in (0, 1):
        issues.append("IHDR interlace=%d (want 0/1)" % il)
    if bd not in VALID_BD.get(ct, ()):
        issues.append("bit depth %d invalid for color type %d" % (bd, ct))
    if w == 0 or h == 0:
        issues.append("zero dimension")
    if ct == 3 and b"PLTE" not in types:
        issues.append("color type 3 requires a PLTE chunk")
    if b"IDAT" not in types:
        issues.append("no IDAT chunk")
    crc_bad = [t.decode("latin-1", "replace") for t, _, ok in chunks if not ok]
    if crc_bad:
        issues.append("CRC mismatch in chunk(s): %s" % ", ".join(crc_bad))
    if trailing:
        issues.append("%d trailing byte(s) after IEND" % trailing)

    idat = b"".join(p for t, p, _ in chunks if t == b"IDAT")
    idat_sizes = [len(p) for t, p, _ in chunks if t == b"IDAT"]
    anc = [(t.decode("latin-1", "replace"), 12 + len(p))
           for t, p, _ in chunks if t not in CRITICAL]

    lines = None
    stats = None
    raw = None
    raw_len = 0
    zlib_trailing = 0
    if do_pixel and idat:
        try:
            dobj = zlib.decompressobj()
            raw = dobj.decompress(idat)
            try:
                raw += dobj.flush()
            except Exception:
                pass
            zlib_trailing = len(dobj.unused_data)
            raw_len = len(raw)
            if raw_len > MAX_RAW_WORK:
                print("note: raw pixel data %s too large, pixel analysis skipped"
                      % human(raw_len), file=sys.stderr)
                raw = None
            else:
                lines, leftover = unfilter(raw, w, h, bd, ct, il)
                if leftover:
                    issues.append("%d unused byte(s) at end of raw image data" % leftover)
                stats = pixel_stats(lines, ct, bd)
        except zlib.error as e:
            issues.append("IDAT zlib stream error: %s" % e)
            raw = None
        except ValueError as e:
            issues.append("pixel decode failed: %s" % e)
    if zlib_trailing:
        issues.append("%d trailing byte(s) after IDAT zlib stream" % zlib_trailing)

    # ---- 生成线索 ----
    hints = []
    total_est = 0

    def rank_for(saving):
        pct = saving / float(filesize) if filesize else 0
        return 0 if pct >= 0.20 else (1 if pct >= 0.05 else 2)

    if stats:
        cands = conversion_candidates(lines, ct, bd, stats, len(idat))
        if cands:
            cands.sort(key=lambda t: -t[1])
            text, saving = cands[0]
            hints.append((rank_for(saving),
                          "%s: saves ~%s (%.1f%%)" % (text, human(saving),
                                                      saving * 100.0 / filesize)))
            total_est += saving
            for text2, saving2 in cands[1:]:
                hints.append((3, "also possible: %s (~%s, overlaps the main hint)"
                              % (text2, human(saving2))))

    if anc:
        total_anc = sum(s for _, s in anc)
        names = ", ".join(sorted(n for n, _ in anc))
        msg = "strip ancillary chunks (%s): ~%s" % (names, human(total_anc))
        if "pHYs" in names:
            msg += " -- keep pHYs if the DPI metadata matters"
        rank = 1 if (total_anc >= 128 and total_anc * 20 >= filesize) else \
               (2 if total_anc >= 32 else 3)
        hints.append((rank, msg))
        if rank != 3:
            total_est += total_anc
    else:
        hints.append((3, "no ancillary chunks: already clean"))

    flevel_desc = "n/a"
    if len(idat) >= 2 and (idat[0] & 0x0F) == 8 and (idat[0] >> 4) == 7:
        flevel_desc = ("fastest", "fast", "default", "maximum")[idat[1] >> 6]
    if raw is not None:
        re9 = len(zlib.compress(raw, 9))
        rs = len(idat) - re9
        if rs > 32:
            hints.append((2, "recompress raw pixels with zlib level 9: saves ~%s "
                             "(mutually exclusive with mode conversions)" % human(rs)))

    if len(idat_sizes) == 1:
        hints.append((3, "single IDAT chunk: reasonable"))
    else:
        avg = len(idat) / len(idat_sizes)
        if avg < 4096:
            hints.append((3, "IDAT split into %d small chunks (avg %d B): re-encoding "
                             "usually merges them (cosmetic)" % (len(idat_sizes), avg)))
        else:
            hints.append((3, "IDAT chunking: %d chunks, avg %d B: reasonable"
                          % (len(idat_sizes), avg)))

    if il == 1:
        hints.append((1, "Adam7 interlacing: typically +10~50% size; turn it off "
                         "unless progressive display is needed"))
    if lines:
        fts = Counter(ft for _, _, ft in lines)
        if set(fts) == {0}:
            if stats and stats["n_colors"] > 64 and ct in (2, 6) and not stats["all_gray"]:
                hints.append((2, "every scanline uses filter 0 (None): adaptive "
                                 "filtering (Sub/Up/Average/Paeth) may help photographic content"))
            else:
                hints.append((3, "filter 0 on all scanlines: fine for low-color images"))
        else:
            hints.append((3, "adaptive filtering in use (filter mix: %s)" % dict(fts)))

    if ct == 3 and stats:
        plte = next((p for t, p, _ in chunks if t == b"PLTE"), b"")
        n_pal = len(plte) // 3
        used_n = len(stats["used"])
        if 0 < used_n < n_pal:
            saving = 3 * (n_pal - used_n)
            bits_needed = max(1, (used_n - 1).bit_length())
            extra = "; index depth could drop to %d-bit" % bits_needed if bits_needed < bd else ""
            hints.append((2 if saving >= 32 else 3,
                          "palette has %d entries but only %d used: trim it (saves ~%s)%s"
                          % (n_pal, used_n, human(saving), extra)))
            if saving >= 32:
                total_est += saving

    out = []
    out.append("== PNG optimization report ==")
    out.append("file      : %s" % os.path.abspath(path))
    out.append("file size : %s" % human(filesize))
    out.append("chunks    : %d (%s)" % (len(chunks),
                                        " ".join(t.decode("latin-1", "replace") for t in types)))
    out.append("image     : %dx%d, %s, depth %d, interlace %d"
               % (w, h, COLOR_NAMES.get(ct, ct), bd, il))
    ratio = (len(idat) * 100.0 / raw_len) if raw_len else 0.0
    out.append("IDAT      : %d chunk(s), %s compressed -> %s raw (ratio %.1f%%)"
               % (len(idat_sizes), human(len(idat)), human(raw_len), ratio))
    if stats:
        alpha = ("fully opaque" if stats["all_opaque"]
                 else "n/a" if stats["all_opaque"] is None else "has transparency")
        gray = ("n/a" if stats["all_gray"] is None else
                ("yes" if stats["all_gray"] else "no"))
        out.append("pixels    : %s px, %d unique color value(s), alpha %s, gray %s"
                   % ("{:,}".format(stats["n_pixels"]), stats["n_colors"], alpha, gray))
    if issues:
        out.append("")
        out.append("warnings/issues:")
        for s in issues:
            out.append("  [!] " + s)
    out.append("")
    out.append("hints (by impact):")
    if hints:
        for rank, msg in sorted(hints, key=lambda t: t[0]):
            out.append("  [%s] %s" % (SEV[rank], msg))
    else:
        out.append("  (none - file looks already well optimized)")
    if total_est > 0 and filesize:
        out.append("estimated total saving: ~%s (%.1f%%) -- hints overlap; "
                   "real gain requires re-encoding"
                   % (human(total_est), total_est * 100.0 / filesize))
    return "\n".join(out)


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        prog="png-optimize-report",
        description="Analyze a PNG and report actionable size-optimization hints "
                    "(palette conversion, ancillary chunks, recompression, etc).")
    ap.add_argument("png", help="PNG file to analyze")
    ap.add_argument("--no-pixel", action="store_true",
                    help="only inspect chunk structure, skip pixel decoding")
    args = ap.parse_args(argv)
    try:
        print(analyze(args.png, do_pixel=not args.no_pixel))
    except (ValueError, OSError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
