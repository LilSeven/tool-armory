#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图片清单 Markdown 表 — 生成含尺寸与文件大小的 Markdown 表格。

用途:
    扫描目录中的图片（PNG / JPEG / GIF / BMP / WEBP，仅读文件头判尺寸），
    生成一张可直接贴入文档或 issue 的 Markdown 表格：文件路径、宽×高、
    像素面积、文件大小。

示例命令:
    python img-markdown-table.py screenshots
    python img-markdown-table.py screenshots -r --sort area -n 20
    python img-markdown-table.py screenshots --absolute -o table.md

参数速查:
    directory            要扫描的目录，默认当前目录
    -r, --recursive      递归扫描子目录
    -n, --top N          只输出前 N 行（按排序规则取前 N，0=全部，默认 0）
    --sort {name,area,size}
                         排序: name=路径升序(默认), area=像素面积降序,
                         size=文件大小降序
    --absolute           文件列输出绝对路径（默认输出相对路径）
    -o, --output FILE    把表格写入 Markdown 文件（UTF-8），默认打印到屏幕

说明:
    仅使用 Python 标准库；输出强制 UTF-8。
    退出码: 0=成功，2=目录不存在等用法错误。
    无法读取尺寸的文件（坏图/占位文件）会在表中标注“读取失败”。
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


def md_escape(text):
    """转义 Markdown 表格单元格中的竖线。"""
    return text.replace("|", "\\|")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="img-markdown-table.py",
        description="生成含尺寸与文件大小的 Markdown 表格，方便贴入文档或 issue。",
    )
    parser.add_argument("directory", nargs="?", default=".",
                        help="要扫描的目录（默认当前目录）")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="递归扫描子目录")
    parser.add_argument("-n", "--top", type=int, default=0, metavar="N",
                        help="只输出前 N 行（按排序规则取前 N，0=全部）")
    parser.add_argument("--sort", choices=("name", "area", "size"), default="name",
                        help="排序: name=路径升序(默认), area=像素面积降序, size=文件大小降序")
    parser.add_argument("--absolute", action="store_true",
                        help="文件列输出绝对路径（默认输出相对路径）")
    parser.add_argument("-o", "--output", metavar="FILE",
                        help="把 Markdown 表格写入文件（UTF-8）而不是打印")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.directory):
        print("错误: 目录不存在或不是目录: %s" % args.directory, file=sys.stderr)
        return 2
    if args.top < 0:
        parser.error("-n/--top 不能为负数")

    base = os.path.abspath(args.directory)
    records = collect_records(base, args.recursive)

    def sort_key(rec):
        path, dims, fsize = rec
        readable = 0 if dims else 1
        if args.sort == "area":
            area = dims[0] * dims[1] if dims else 0
            return (readable, -area, -fsize, path.lower())
        if args.sort == "size":
            return (readable, -fsize, path.lower())
        return (readable, path.lower())

    records.sort(key=sort_key)
    shown = records[:args.top] if args.top else records

    lines = ["| 文件 | 尺寸 | 像素 | 文件大小 |",
             "| :--- | ---: | ---: | ---: |"]
    for path, dims, fsize in shown:
        display = os.path.abspath(path) if args.absolute else os.path.relpath(path, base)
        if dims:
            dim_cell = "%d×%d" % dims
            area_cell = "{:,}".format(dims[0] * dims[1])
        else:
            dim_cell = "读取失败"
            area_cell = "-"
        lines.append("| %s | %s | %s | %s |" %
                     (md_escape(display), dim_cell, area_cell, human_size(fsize)))

    broken = sum(1 for _, dims, _ in records if dims is None)
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        print("已写入 %s（%d 张图片，其中 %d 张读取失败）"
              % (args.output, len(records), broken), file=sys.stderr)
    else:
        print("\n".join(lines))
        print("<!-- 共 %d 张图片，其中 %d 张读取失败 -->" % (len(records), broken))
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
