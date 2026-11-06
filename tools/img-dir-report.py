#!/usr/bin/env python3
"""目录图片报表（img-dir-report）。

扫描目录中的图片文件（默认不递归），输出对齐表格:
文件名、格式、宽高、文件大小、修改时间。
支持 PNG/JPEG/GIF/BMP/WEBP/TIFF，仅用标准库解析文件头，不依赖 PIL。

示例:
    python img-dir-report.py D:/pics
    python img-dir-report.py . -r --sort size --desc
    python img-dir-report.py images --ext png,jpg --json

退出码: 0=正常（个别文件解析失败会在表后列出，不影响其余行）; 2=路径不存在。
"""

import argparse
import json
import os
import struct
import sys
import unicodedata
from datetime import datetime

# --------------------------------------------------------------------------
# 图像头解析（仅标准库）：支持 PNG / JPEG / GIF / BMP / WEBP / TIFF
# --------------------------------------------------------------------------

DEFAULT_EXTS = (".png", ".jpg", ".jpeg", ".jpe", ".gif", ".bmp", ".dib",
                ".webp", ".tif", ".tiff")

_TIFF_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}

_EXIF_TAGS = {
    0x0100: "ImageWidth", 0x0101: "ImageHeight", 0x010F: "Make", 0x0110: "Model",
    0x0112: "Orientation", 0x011A: "XResolution", 0x011B: "YResolution",
    0x0128: "ResolutionUnit", 0x0132: "DateTime", 0x8827: "ISOSpeedRatings",
    0x9003: "DateTimeOriginal", 0x9004: "DateTimeDigitized",
}


def _tiff_scalar(data, bo, typ, count, raw):
    """把一个 TIFF 字段解码为标量/字符串；不支持或损坏时返回 None。"""
    try:
        if typ == 2:  # ASCII
            return raw.split(b"\x00", 1)[0].decode("utf-8", "replace").strip()
        if typ in (1, 3, 4, 6, 8, 9):  # 整数族
            f = {1: "B", 3: "H", 4: "I", 6: "b", 8: "h", 9: "i"}[typ]
            vals = struct.unpack(bo + f * count, raw[:count * _TIFF_SIZES[typ]])
            return vals[0] if count == 1 else list(vals)
        if typ in (5, 10):  # (有符号)分数
            f = "I" if typ == 5 else "i"
            vals = struct.unpack(bo + f * (2 * count), raw[:8 * count])
            fr = [(vals[i] / vals[i + 1]) if vals[i + 1] else None
                  for i in range(0, 2 * count, 2)]
            return fr[0] if count == 1 else fr
    except (struct.error, KeyError):
        return None
    return None


def parse_tiff_tags(data):
    """解析 TIFF 结构（IFD0 + Exif 子 IFD），返回 {标签名: 值}。"""
    tags = {}
    if len(data) < 8 or data[:2] not in (b"II", b"MM"):
        return tags
    bo = "<" if data[:2] == b"II" else ">"
    try:
        if struct.unpack_from(bo + "H", data, 2)[0] != 42:
            return tags
        ifd0 = struct.unpack_from(bo + "I", data, 4)[0]
    except struct.error:
        return tags

    def read_ifd(off, dest):
        """解析单个 IFD，返回 Exif 子 IFD 偏移（无则 None）。"""
        if off <= 0 or off + 2 > len(data):
            return None
        try:
            n = struct.unpack_from(bo + "H", data, off)[0]
        except struct.error:
            return None
        if not 0 < n <= 1024:
            return None
        exif_ptr = None
        p = off + 2
        for _ in range(n):
            if p + 12 > len(data):
                break
            tag, typ, cnt = struct.unpack_from(bo + "HHI", data, p)
            vf = data[p + 8:p + 12]
            p += 12
            size = _TIFF_SIZES.get(typ)
            if size is None:
                continue
            total = size * cnt
            if total <= 4:
                raw = vf[:total]
            else:
                try:
                    vo = struct.unpack_from(bo + "I", vf)[0]
                except struct.error:
                    continue
                if vo + total > len(data):
                    continue
                raw = data[vo:vo + total]
            if tag == 0x8769:  # Exif 子 IFD 指针
                v = _tiff_scalar(data, bo, typ, cnt, raw)
                if isinstance(v, int):
                    exif_ptr = v
                continue
            name = _EXIF_TAGS.get(tag)
            if name and name not in dest:
                dest[name] = _tiff_scalar(data, bo, typ, cnt, raw)
        return exif_ptr

    sub_ptr = read_ifd(ifd0, tags)
    if sub_ptr:
        sub = {}
        read_ifd(sub_ptr, sub)
        for key, val in sub.items():
            tags.setdefault(key, val)
    return tags


def _info(fmt):
    return {"format": fmt, "width": None, "height": None,
            "dpi_x": None, "dpi_y": None, "exif": {}}


def parse_png(data):
    info = _info("PNG")
    info["width"] = struct.unpack_from(">I", data, 16)[0]
    info["height"] = struct.unpack_from(">I", data, 20)[0]
    exif_blob = None
    off = 8
    while off + 8 <= len(data):
        clen = struct.unpack_from(">I", data, off)[0]
        ctype = data[off + 4:off + 8]
        cstart = off + 8
        if ctype == b"pHYs" and clen >= 9 and cstart + 9 <= len(data):
            px, py, unit = struct.unpack_from(">IIB", data, cstart)
            if unit == 1 and px and py:  # 1=米制, 像素/米 → DPI
                info["dpi_x"] = round(px * 0.0254, 1)
                info["dpi_y"] = round(py * 0.0254, 1)
        elif ctype == b"eXIf" and clen >= 8:
            exif_blob = data[cstart:cstart + clen]
        if ctype == b"IEND":
            break
        off = cstart + clen + 4  # 跳过 CRC
    if exif_blob:
        info["exif"] = parse_tiff_tags(exif_blob)
    return info


def parse_jpeg(data):
    info = _info("JPEG")
    jfif = None
    exif_blob = None
    i, n = 2, len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            break
        while i < n and data[i] == 0xFF:
            i += 1
        if i >= n:
            break
        marker = data[i]
        i += 1
        if marker == 0x01 or 0xD0 <= marker <= 0xD9:  # 无长度段
            if marker == 0xD9:
                break
            continue
        if i + 2 > n:
            break
        seglen = struct.unpack_from(">H", data, i)[0]
        if seglen < 2 or i + seglen > n:
            break
        seg = data[i + 2:i + seglen]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if info["width"] is None and len(seg) >= 5:
                info["height"] = struct.unpack_from(">H", seg, 1)[0]
                info["width"] = struct.unpack_from(">H", seg, 3)[0]
        elif marker == 0xE1 and seg[:6] == b"Exif\x00\x00" and exif_blob is None:
            exif_blob = seg[6:]
        elif marker == 0xE0 and seg[:5] == b"JFIF\x00" and len(seg) >= 12 and jfif is None:
            jfif = (seg[7], struct.unpack_from(">H", seg, 8)[0],
                    struct.unpack_from(">H", seg, 10)[0])
        i += seglen
    if jfif and jfif[0] in (1, 2) and jfif[1]:  # 0=只有宽高比, 1=英寸, 2=厘米
        k = 1.0 if jfif[0] == 1 else 2.54
        info["dpi_x"] = round(jfif[1] * k, 1)
        info["dpi_y"] = round(jfif[2] * k, 1)
    if exif_blob:
        info["exif"] = parse_tiff_tags(exif_blob)
        exif = info["exif"]
        if info["dpi_x"] is None and exif.get("XResolution") \
                and exif.get("ResolutionUnit") in (2, 3):
            k = 1.0 if exif["ResolutionUnit"] == 2 else 2.54
            info["dpi_x"] = round(exif["XResolution"] * k, 1)
            info["dpi_y"] = round((exif.get("YResolution") or exif["XResolution"]) * k, 1)
    return info


def parse_gif(data):
    info = _info("GIF")
    info["width"] = struct.unpack_from("<H", data, 6)[0]
    info["height"] = struct.unpack_from("<H", data, 8)[0]
    return info


def parse_bmp(data):
    info = _info("BMP")
    hsize = struct.unpack_from("<I", data, 14)[0]
    if hsize == 12:  # BITMAPCOREHEADER
        info["width"] = struct.unpack_from("<H", data, 18)[0]
        info["height"] = struct.unpack_from("<H", data, 20)[0]
        return info
    info["width"] = abs(struct.unpack_from("<i", data, 18)[0])
    info["height"] = abs(struct.unpack_from("<i", data, 22)[0])
    if hsize >= 40 and len(data) >= 46:  # BITMAPINFOHEADER 起有分辨率字段
        xppm, yppm = struct.unpack_from("<ii", data, 38)
        if xppm > 0:
            info["dpi_x"] = round(xppm * 0.0254, 1)
        if yppm > 0:
            info["dpi_y"] = round(yppm * 0.0254, 1)
    return info


def parse_webp(data):
    info = _info("WEBP")
    off = 12
    while off + 8 <= len(data):
        fourcc = data[off:off + 4]
        csize = struct.unpack_from("<I", data, off + 4)[0]
        body = data[off + 8:off + 8 + csize]
        if fourcc == b"VP8X" and len(body) >= 10:
            info["width"] = 1 + (body[4] | body[5] << 8 | body[6] << 16)
            info["height"] = 1 + (body[7] | body[8] << 8 | body[9] << 16)
        elif fourcc == b"VP8 " and len(body) >= 10 and body[3:6] == b"\x9d\x01\x2a":
            info["width"] = struct.unpack_from("<H", body, 6)[0] & 0x3FFF
            info["height"] = struct.unpack_from("<H", body, 8)[0] & 0x3FFF
        elif fourcc == b"VP8L" and len(body) >= 5 and body[0] == 0x2F:
            bits = int.from_bytes(body[1:5], "little")
            info["width"] = (bits & 0x3FFF) + 1
            info["height"] = ((bits >> 14) & 0x3FFF) + 1
        elif fourcc == b"EXIF" and body:
            info["exif"] = parse_tiff_tags(body)
        off += 8 + csize + (csize & 1)
    return info


def parse_tiff_file(data):
    info = _info("TIFF")
    tags = parse_tiff_tags(data)
    info["width"] = tags.get("ImageWidth")
    info["height"] = tags.get("ImageHeight")
    info["exif"] = {k: v for k, v in tags.items()
                    if k not in ("ImageWidth", "ImageHeight")}
    if tags.get("XResolution") and tags.get("ResolutionUnit") in (2, 3):
        k = 1.0 if tags["ResolutionUnit"] == 2 else 2.54
        info["dpi_x"] = round(tags["XResolution"] * k, 1)
        info["dpi_y"] = round((tags.get("YResolution") or tags["XResolution"]) * k, 1)
    return info


def read_image_info(path):
    """读取单张图片，返回 {format,width,height,dpi_x,dpi_y,exif}；失败抛异常。"""
    with open(path, "rb") as fh:
        data = fh.read()
    head = data[:12]
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return parse_png(data)
    if head[:2] == b"\xff\xd8":
        return parse_jpeg(data)
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return parse_gif(data)
    if head[:2] == b"BM" and len(data) >= 26:
        return parse_bmp(data)
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return parse_webp(data)
    if head[:2] in (b"II", b"MM"):
        return parse_tiff_file(data)
    raise ValueError("无法识别的图片格式")


def collect_entry(path, root=None):
    """收集单个文件的元数据条目（解析失败不抛出，记入 error 字段）。"""
    st = os.stat(path)
    if root:
        try:
            rel = os.path.relpath(path, root)
        except ValueError:  # Windows 跨盘符
            rel = path
    else:
        rel = path
    entry = {"file": rel.replace("\\", "/"), "name": os.path.basename(path),
             "size_bytes": st.st_size,
             "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")}
    try:
        info = read_image_info(path)
    except Exception as exc:  # 单文件失败不中断整批
        entry.update({"format": "?", "width": None, "height": None,
                      "dpi_x": None, "dpi_y": None, "exif": {},
                      "error": "%s: %s" % (type(exc).__name__, exc)})
        return entry
    entry.update(info)
    entry["error"] = None
    ex = info.get("exif") or {}
    entry["orientation"] = ex.get("Orientation")
    entry["make"] = ex.get("Make")
    entry["model"] = ex.get("Model")
    entry["exif_datetime"] = ex.get("DateTime")
    entry["exif_datetime_original"] = ex.get("DateTimeOriginal")
    entry["exif_datetime_digitized"] = ex.get("DateTimeDigitized")
    return entry


def parse_exts(text):
    if not text:
        return set(DEFAULT_EXTS)
    return {"." + x.strip().lstrip(".").lower() for x in text.split(",") if x.strip()}


def iter_images(roots, recursive, exts):
    """按给定路径收集图片文件；显式给出的文件不做扩展名过滤。"""
    for root in roots:
        if os.path.isfile(root):
            yield root
            continue
        if recursive:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames.sort()
                for fn in sorted(filenames):
                    if os.path.splitext(fn)[1].lower() in exts:
                        yield os.path.join(dirpath, fn)
        else:
            for fn in sorted(os.listdir(root)):
                p = os.path.join(root, fn)
                if os.path.isfile(p) and os.path.splitext(fn)[1].lower() in exts:
                    yield p


# --------------------------------------------------------------------------
# 展示辅助（全角字符按 2 列宽对齐）
# --------------------------------------------------------------------------

def dwidth(text):
    return sum(2 if unicodedata.east_asian_width(ch) in "FW" else 1 for ch in text)


def pad(text, width, right=False):
    gap = " " * max(0, width - dwidth(text))
    return gap + text if right else text + gap


def clip(text, width):
    if dwidth(text) <= width:
        return text
    out = ""
    for ch in text:
        if dwidth(out) + dwidth(ch) > width - 2:
            break
        out += ch
    return out + ".."


def human(n):
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return "%d %s" % (int(size), unit) if unit == "B" else "%.1f %s" % (size, unit)
        size /= 1024.0


# --------------------------------------------------------------------------
# 主体逻辑
# --------------------------------------------------------------------------

def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(
        prog="img-dir-report", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("directory", nargs="?", default=".",
                    help="要扫描的目录（默认当前目录，也可给单个图片文件）")
    ap.add_argument("-r", "--recursive", action="store_true", help="递归扫描子目录")
    ap.add_argument("--sort", choices=("name", "size", "mtime", "pixels"),
                    default="name", help="排序依据（默认 name）")
    ap.add_argument("--desc", action="store_true", help="倒序排列")
    ap.add_argument("--ext", help="逗号分隔的扩展名过滤（默认内置图片后缀）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    target = args.directory
    if not os.path.exists(target):
        print("错误: 路径不存在: %s" % target, file=sys.stderr)
        return 2
    is_dir = os.path.isdir(target)
    exts = parse_exts(args.ext)
    entries = [collect_entry(f, target if is_dir else None)
               for f in iter_images([target], args.recursive, exts)]
    keymap = {
        "name": lambda e: e["name"].lower(),
        "size": lambda e: e["size_bytes"],
        "mtime": lambda e: e["mtime"],
        "pixels": lambda e: (e["width"] or 0) * (e["height"] or 0),
    }
    entries.sort(key=keymap[args.sort], reverse=args.desc)

    if args.json:
        print(json.dumps({"directory": target, "recursive": args.recursive,
                          "count": len(entries),
                          "ok_count": sum(1 for e in entries if not e["error"]),
                          "error_count": sum(1 for e in entries if e["error"]),
                          "images": entries}, ensure_ascii=False, indent=2))
        return 0

    if not entries:
        print("未找到图片文件（路径: %s, 递归: %s）" %
              (target, "是" if args.recursive else "否"))
        return 0

    w_name = max(dwidth("文件名"), min(48, max(dwidth(e["file"]) for e in entries)))
    w_fmt = max(dwidth("格式"), max(dwidth(e["format"]) for e in entries))
    dims = ["%dx%d" % (e["width"], e["height"]) if e["width"] and e["height"] else "-"
            for e in entries]
    w_dim = max(dwidth("尺寸"), max(len(d) for d in dims))
    sizes = [human(e["size_bytes"]) for e in entries]
    w_size = max(dwidth("大小"), max(len(s) for s in sizes))

    head = (pad("文件名", w_name + 2) + pad("格式", w_fmt + 2) +
            pad("尺寸", w_dim + 2, right=True) + pad("大小", w_size + 2, right=True) +
            "  修改时间")
    line = "-" * max(40, dwidth(head))
    print(head)
    print(line)
    for e, dim, sz in zip(entries, dims, sizes):
        print(pad(clip(e["file"], w_name), w_name + 2) + pad(e["format"], w_fmt + 2) +
              pad(dim, w_dim + 2, right=True) + pad(sz, w_size + 2, right=True) +
              "  " + e["mtime"])
    print(line)
    total = sum(e["size_bytes"] for e in entries)
    failed = [e for e in entries if e["error"]]
    print("合计 %d 张 | %s | 解析失败 %d | 排序: %s%s" %
          (len(entries), human(total), len(failed), args.sort,
           " 倒序" if args.desc else ""))
    for e in failed:
        print("  ! %s → %s" % (e["file"], e["error"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
