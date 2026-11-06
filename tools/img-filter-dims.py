#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""尺寸条件筛选 — 按最小/最大宽高条件筛选并列出符合条件的图片。

用途:
    扫描目录中的图片（PNG / JPEG / GIF / BMP / WEBP，仅读文件头判尺寸），
    按 宽>=N / 宽<=N / 高>=N / 高<=N 的组合条件（AND）筛选并列出，
    结果按像素面积降序显示。不指定条件时列出全部图片。

示例命令:
    python img-filter-dims.py screenshots --min-width 800
    python img-filter-dims.py screenshots -r --min-width 100 --max-width 700 --min-height 50
    python img-filter-dims.py screenshots --min-height 1080

参数速查:
    directory        要扫描的目录，默认当前目录
    --min-width N    宽度 >= N
    --max-width N    宽度 <= N
    --min-height N   高度 >= N
    --max-height N   高度 <= N
    -r, --recursive  递归扫描子目录

说明:
    仅使用 Python 标准库；输出强制 UTF-8。
    退出码: 0=成功，2=用法错误（如目录不存在、min>max）。
    无法读取尺寸的坏图无法参与条件判断，一律跳过并在末尾提示数量。
"""

import argparse
import os
import sys

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
_MAX_PROBE = 2 * 1024 * 1024  # 识别图片头最多读取的字节数


def _parse_jpeg(data):
    """从 JPEG（含渐进式）字节流中扫描 SOFn 段取尺寸。"""
    pos, n = 2, len(data)
    while pos + 4 <= n:
        if data[pos] != 0xFF:
            pos += 1
            continue
        while pos < n and data[pos] == 0xFF:
            pos += 1
        if pos >= n:
            break
        marker = data[pos]
        pos += 1
        if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
            continue  # 无长度字段的段
        if marker in (0xD9, 0xDA):
            break  # 到 EOI/SOS 仍未见到 SOF
        if pos + 2 > n:
            break
        seg_len = int.from_bytes(data[pos:pos + 2], "big")
        if seg_len < 2:
            break
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if pos + 7 > n:
                break
            height = int.from_bytes(data[pos + 3:pos + 5], "big")
            width = int.from_bytes(data[pos + 5:pos + 7], "big")
            return (width, height) if width and height else None
        pos += seg_len
    return None


def _parse_webp(data):
    """从 RIFF/WEBP 字节流中按 chunk 取尺寸（VP8X / VP8 / VP8L）。"""
    pos, n = 12, len(data)
    while pos + 8 <= n:
        fourcc = data[pos:pos + 4]
        size = int.from_bytes(data[pos + 4:pos + 8], "little")
        body = data[pos + 8:pos + 8 + size]
        if fourcc == b"VP8X" and len(body) >= 10:
            return (int.from_bytes(body[4:7], "little") + 1,
                    int.from_bytes(body[7:10], "little") + 1)
        if fourcc == b"VP8 " and len(body) >= 10 and body[3:6] == b"\x9d\x01\x2a":
            return (int.from_bytes(body[6:8], "little") & 0x3FFF,
                    int.from_bytes(body[8:10], "little") & 0x3FFF)
        if fourcc == b"VP8L" and len(body) >= 5 and body[0] == 0x2F:
            bits = int.from_bytes(body[1:5], "little")
            return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        pos += 8 + size + (size & 1)  # chunk 按 2 字节对齐
    return None


def parse_size(path):
    """读取图片头信息，返回 (宽, 高)；无法识别或文件损坏时返回 None。"""
    try:
        with open(path, "rb") as fh:
            data = fh.read(_MAX_PROBE)
    except OSError:
        return None
    if len(data) < 10:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        return (width, height) if width and height else None
    if data[:6] in (b"GIF87a", b"GIF89a"):
        width = int.from_bytes(data[6:8], "little")
        height = int.from_bytes(data[8:10], "little")
        return (width, height) if width and height else None
    if data[:2] == b"BM" and len(data) >= 26:
        hdr = int.from_bytes(data[14:18], "little")
        if hdr == 12:  # BITMAPCOREHEADER（OS/2）
            width = int.from_bytes(data[18:20], "little")
            height = int.from_bytes(data[20:22], "little")
        else:
            width = int.from_bytes(data[18:22], "little", signed=True)
            height = int.from_bytes(data[22:26], "little", signed=True)
        return (width, abs(height)) if width > 0 and height else None
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _parse_webp(data)
    if data[:2] == b"\xff\xd8":
        return _parse_jpeg(data)
    return None


def iter_image_files(root, recursive):
    """产出目录（可选递归）中扩展名匹配的图片文件路径，按名称排序。"""
    if recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort(key=str.lower)
            for name in sorted(filenames, key=str.lower):
                if os.path.splitext(name)[1].lower() in IMAGE_EXTS:
                    yield os.path.join(dirpath, name)
    else:
        try:
            names = os.listdir(root)
        except OSError:
            return
        for name in sorted(names, key=str.lower):
            path = os.path.join(root, name)
            if os.path.isfile(path) and os.path.splitext(name)[1].lower() in IMAGE_EXTS:
                yield path


def collect_records(root, recursive):
    """返回 [(路径, (宽, 高) 或 None, 文件字节数), ...]。"""
    records = []
    for path in iter_image_files(root, recursive):
        dims = parse_size(path)
        try:
            fsize = os.path.getsize(path)
        except OSError:
            fsize = 0
        records.append((path, dims, fsize))
    return records


def human_size(num):
    """字节数转成人类可读字符串，如 12 B / 34.5 KB / 2.3 MB。"""
    if num < 1024:
        return "%d B" % num
    size = float(num)
    for unit in ("KB", "MB", "GB", "TB"):
        size /= 1024.0
        if size < 1024 or unit == "TB":
            return "%.1f %s" % (size, unit)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="img-filter-dims.py",
        description="按最小/最大宽高条件筛选并列出符合条件的图片。",
    )
    parser.add_argument("directory", nargs="?", default=".",
                        help="要扫描的目录（默认当前目录）")
    parser.add_argument("--min-width", type=int, metavar="N", help="宽度 >= N")
    parser.add_argument("--max-width", type=int, metavar="N", help="宽度 <= N")
    parser.add_argument("--min-height", type=int, metavar="N", help="高度 >= N")
    parser.add_argument("--max-height", type=int, metavar="N", help="高度 <= N")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="递归扫描子目录")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.directory):
        print("错误: 目录不存在或不是目录: %s" % args.directory, file=sys.stderr)
        return 2
    if (args.min_width is not None and args.max_width is not None
            and args.min_width > args.max_width):
        parser.error("--min-width 不能大于 --max-width")
    if (args.min_height is not None and args.max_height is not None
            and args.min_height > args.max_height):
        parser.error("--min-height 不能大于 --max-height")

    def matches(dims):
        width, height = dims
        if args.min_width is not None and width < args.min_width:
            return False
        if args.max_width is not None and width > args.max_width:
            return False
        if args.min_height is not None and height < args.min_height:
            return False
        if args.max_height is not None and height > args.max_height:
            return False
        return True

    base = os.path.abspath(args.directory)
    records = collect_records(base, args.recursive)
    readable = [rec for rec in records if rec[1]]
    matched = [rec for rec in readable if matches(rec[1])]
    matched.sort(key=lambda rec: (-(rec[1][0] * rec[1][1]), rec[0].lower()))

    conds = []
    if args.min_width is not None:
        conds.append("宽>=%d" % args.min_width)
    if args.max_width is not None:
        conds.append("宽<=%d" % args.max_width)
    if args.min_height is not None:
        conds.append("高>=%d" % args.min_height)
    if args.max_height is not None:
        conds.append("高<=%d" % args.max_height)
    cond_text = " ".join(conds) if conds else "无（列出全部图片）"
    print("条件: %s（目录: %s，%s）" % (
        cond_text, base, "递归" if args.recursive else "仅当前层"))
    print("%11s  %10s  %s" % ("尺寸", "像素", "路径"))
    for path, dims, fsize in matched:
        print("%11s  %12s  %s  (%s)" % (
            "%d×%d" % dims, "{:,}".format(dims[0] * dims[1]),
            os.path.relpath(path, base), human_size(fsize)))
    print("匹配 %d / %d 张图片（%d 张无法读取尺寸，已跳过）" % (
        len(matched), len(records), len(records) - len(readable)))
    return 0


def _force_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


if __name__ == "__main__":
    _force_utf8_stdio()
    sys.exit(main())
