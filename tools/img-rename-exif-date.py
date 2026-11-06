#!/usr/bin/env python3
"""img-rename-exif-date —— 依据 EXIF 拍摄时间改名为 IMG_20240101_123456 式。

从 EXIF 读取拍摄时间（优先 DateTimeOriginal，其次 DateTimeDigitized、
DateTime），把照片改名为 IMG_YYYYMMDD_HHMMSS.原扩展名；文件名已符合该
格式时跳过，目标重名时自动追加 -1、-2 后缀。默认 dry-run 预览，加
-x/--exec 才真正改名；没有 EXIF 拍摄时间的文件默认跳过，加 --mtime 可
回退用文件修改时间。只用 Python 标准库。

用法:
    python img-rename-exif-date.py <文件或目录>... [-r] [--mtime] [-x]

示例命令:
    python img-rename-exif-date.py D:/photos             # 预览
    python img-rename-exif-date.py D:/photos -x          # 实际执行改名
    python img-rename-exif-date.py D:/photos --mtime -x  # 无 EXIF 时用修改时间

说明:
    * 按文件头签名识别 JPEG/TIFF/PNG/GIF/BMP；PNG/GIF/BMP 通常没有
      EXIF 拍摄时间，默认会被跳过并提示。
"""

import argparse
import datetime
import os
import re
import struct
import sys

DATED_RE = re.compile(r"^IMG_\d{8}_\d{6}$", re.IGNORECASE)

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


def exif_datetime(tags):
    """拍摄时间：DateTimeOriginal > DateTimeDigitized > DateTime。"""
    for tag in (0x9003, 0x9004, 0x0132):
        val = tags.get(tag)
        if isinstance(val, str) and val.strip():
            for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    return datetime.datetime.strptime(val.strip(), fmt)
                except ValueError:
                    pass
    return None


def is_supported_image(path):
    """按文件头签名判断是否为本工具支持的图片容器。"""
    try:
        with open(path, "rb") as f:
            head = f.read(12)
    except OSError:
        return False
    return (head[:2] == b"\xff\xd8"
            or head[:4] in (b"II*\x00", b"MM\x00*")
            or head[:8] == b"\x89PNG\r\n\x1a\n"
            or head[:6] in (b"GIF87a", b"GIF89a")
            or head[:2] == b"BM")


def iter_files(paths, recursive=False):
    """收集目录/文件路径（不筛扩展名，由签名判断）。"""
    for p in paths:
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            if recursive:
                for root, dirs, files in os.walk(p):
                    dirs.sort()
                    for name in sorted(files):
                        yield os.path.join(root, name)
            else:
                try:
                    names = sorted(os.listdir(p))
                except OSError as exc:
                    print("[警告] 无法列出目录 %s: %s" % (p, exc), file=sys.stderr)
                    continue
                for name in names:
                    fp = os.path.join(p, name)
                    if os.path.isfile(fp):
                        yield fp
        else:
            print("[警告] 路径不存在: %s" % p, file=sys.stderr)


def _same_file(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _safe_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _safe_stdio()
    parser = argparse.ArgumentParser(
        prog="img-rename-exif-date",
        description="依据 EXIF 拍摄时间把照片改名为 IMG_YYYYMMDD_HHMMSS 式（默认 dry-run）。",
    )
    parser.add_argument("paths", nargs="+", help="图片文件或目录")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="递归扫描子目录")
    parser.add_argument("--mtime", action="store_true",
                        help="无 EXIF 拍摄时间时回退用文件修改时间")
    parser.add_argument("-x", "--exec", dest="do_exec", action="store_true",
                        help="实际执行改名（默认仅预览）")
    args = parser.parse_args(argv)

    done = planned = kept = no_date = not_img = suffixed = 0
    for fp in iter_files(args.paths, args.recursive):
        if not is_supported_image(fp):
            not_img += 1
            continue
        stem, ext = os.path.splitext(os.path.basename(fp))
        if DATED_RE.match(stem):
            kept += 1
            continue
        dt = exif_datetime(read_exif(fp))
        if dt is None and args.mtime:
            try:
                dt = datetime.datetime.fromtimestamp(os.stat(fp).st_mtime)
            except OSError:
                dt = None
        if dt is None:
            no_date += 1
            print(f"[跳过] {fp}（无 EXIF 拍摄时间）")
            continue
        base = f"IMG_{dt:%Y%m%d_%H%M%S}{ext}"
        d = os.path.dirname(fp)
        cand = base
        k = 1
        while (os.path.exists(os.path.join(d, cand))
               and not _same_file(os.path.join(d, cand), fp)):
            root2, ext2 = os.path.splitext(base)
            cand = f"{root2}-{k}{ext2}"
            k += 1
        if cand != base:
            suffixed += 1
        if args.do_exec:
            os.rename(fp, os.path.join(d, cand))
            print(f"[改名] {os.path.basename(fp)} -> {cand}")
            done += 1
        else:
            print(f"[预览] {os.path.basename(fp)} -> {cand}")
            planned += 1

    mode = "执行" if args.do_exec else "预览（dry-run）"
    n = done if args.do_exec else planned
    extra = f"（其中 {suffixed} 个因重名加了后缀）" if suffixed else ""
    print(f"-- {mode}: 改名 {n} 个{extra}，已是目标命名 {kept} 个，"
          f"无拍摄时间 {no_date} 个，非图片 {not_img} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
