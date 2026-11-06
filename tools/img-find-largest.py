#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最大图片查找 — 按像素面积降序列出目录中前 N 张最大的图片。

用途:
    扫描目录中的图片（PNG / JPEG / GIF / BMP / WEBP，仅读文件头判尺寸），
    按宽×高的像素面积降序排列，列出前 N 张，便于找出体积最大的截图/素材。

示例命令:
    python img-find-largest.py screenshots
    python img-find-largest.py screenshots -r -n 20

参数速查:
    directory        要扫描的目录，默认当前目录
    -n, --top N      列出前 N 张（默认 10，必须 >= 1）
    -r, --recursive  递归扫描子目录

说明:
    仅使用 Python 标准库；输出强制 UTF-8。
    退出码: 0=成功，2=用法错误（如目录不存在、-n 小于 1）。
    无法读取尺寸的坏图不参与排名，只在末尾提示数量。
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
        prog="img-find-largest.py",
        description="按像素面积降序列出目录中前 N 张最大的图片。",
    )
    parser.add_argument("directory", nargs="?", default=".",
                        help="要扫描的目录（默认当前目录）")
    parser.add_argument("-n", "--top", type=int, default=10, metavar="N",
                        help="列出前 N 张（默认 10）")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="递归扫描子目录")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.directory):
        print("错误: 目录不存在或不是目录: %s" % args.directory, file=sys.stderr)
        return 2
    if args.top < 1:
        parser.error("-n/--top 必须 >= 1")

    base = os.path.abspath(args.directory)
    records = collect_records(base, args.recursive)
    ok = [rec for rec in records if rec[1]]
    broken = len(records) - len(ok)
    ok.sort(key=lambda rec: (-(rec[1][0] * rec[1][1]), -rec[2], rec[0].lower()))

    print("目录: %s（%s）" % (base, "递归" if args.recursive else "仅当前层"))
    if not ok:
        print("没有找到能读取尺寸的图片。")
        if broken:
            print("另有 %d 个图片文件无法读取尺寸。" % broken)
        return 0
    print("%4s  %11s  %12s  %10s  %s" % ("#", "尺寸", "像素", "文件大小", "路径"))
    for rank, (path, dims, fsize) in enumerate(ok[:args.top], 1):
        print("%4d  %11s  %12s  %10s  %s" % (
            rank, "%d×%d" % dims, "{:,}".format(dims[0] * dims[1]),
            human_size(fsize), os.path.relpath(path, base)))
    if broken:
        print("（另有 %d 个图片文件无法读取尺寸，未参与排名）" % broken)
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
