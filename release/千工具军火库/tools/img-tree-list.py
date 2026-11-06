#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图片树状列表 — 以树形结构列出目录及子目录中每张图片的尺寸标注。

用途:
    递归遍历目录，用类似 tree 命令的树形缩进展示每一张图片，并在名称后
    附加 [宽×高] 标注（PNG / JPEG / GIF / BMP / WEBP，仅读文件头判尺寸）；
    无法读取尺寸的文件标注 [读取失败]。

示例命令:
    python img-tree-list.py screenshots
    python img-tree-list.py screenshots --depth 2
    python img-tree-list.py screenshots --all

参数速查:
    directory    要扫描的目录，默认当前目录
    --depth N    最多向下展开 N 层（0=不限，默认 0）
    --all        同时显示非图片文件（不加尺寸标注）

说明:
    仅使用 Python 标准库；输出强制 UTF-8。
    退出码: 0=成功，2=目录不存在等用法错误。
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


def _is_dir(entry):
    try:
        return entry.is_dir()
    except OSError:
        return False


def _is_symlink(entry):
    try:
        return entry.is_symlink()
    except OSError:
        return False


def walk_tree(dir_path, prefix, depth, max_depth, show_all, stats, lines):
    """递归渲染一层目录，把行追加到 lines，统计写入 stats。"""
    try:
        entries = list(os.scandir(dir_path))
    except OSError:
        stats["errors"] += 1
        return
    dirs = sorted((e for e in entries if _is_dir(e)), key=lambda e: e.name.lower())
    files = sorted((e for e in entries if not _is_dir(e)), key=lambda e: e.name.lower())
    rows = [(entry, "dir") for entry in dirs]
    for entry in files:
        if os.path.splitext(entry.name)[1].lower() in IMAGE_EXTS:
            rows.append((entry, "image"))
        elif show_all:
            rows.append((entry, "other"))
    for index, (entry, kind) in enumerate(rows):
        last = index == len(rows) - 1
        connector = "└── " if last else "├── "
        child_prefix = prefix + ("    " if last else "│   ")
        if kind == "dir":
            stats["dirs"] += 1
            lines.append(prefix + connector + entry.name + "/")
            if not _is_symlink(entry) and (max_depth is None or depth < max_depth):
                walk_tree(entry.path, child_prefix, depth + 1,
                          max_depth, show_all, stats, lines)
        elif kind == "other":
            lines.append(prefix + connector + entry.name)
        else:
            stats["images"] += 1
            dims = parse_size(entry.path)
            if dims:
                lines.append("%s%s%s  [%d×%d]" % (prefix, connector, entry.name,
                                                  dims[0], dims[1]))
            else:
                stats["broken"] += 1
                lines.append(prefix + connector + entry.name + "  [读取失败]")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="img-tree-list.py",
        description="以树形结构列出目录及子目录中每张图片的尺寸标注。",
    )
    parser.add_argument("directory", nargs="?", default=".",
                        help="要扫描的目录（默认当前目录）")
    parser.add_argument("--depth", type=int, default=0, metavar="N",
                        help="最多向下展开 N 层（0=不限，默认 0）")
    parser.add_argument("--all", action="store_true",
                        help="同时显示非图片文件（不加尺寸标注）")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.directory):
        print("错误: 目录不存在或不是目录: %s" % args.directory, file=sys.stderr)
        return 2
    if args.depth < 0:
        parser.error("--depth 不能为负数")

    base = os.path.abspath(args.directory)
    stats = {"images": 0, "broken": 0, "dirs": 0, "errors": 0}
    lines = []
    walk_tree(base, "", 1, args.depth or None, args.all, stats, lines)

    print(base + os.sep)
    for line in lines:
        print(line)
    print("")
    summary = "共 %d 张图片（%d 张读取失败）· %d 个子目录" % (
        stats["images"], stats["broken"], stats["dirs"])
    if args.depth:
        summary += "· 展开深度 %d" % args.depth
    if stats["errors"]:
        summary += "· %d 个子目录无法读取" % stats["errors"]
    print(summary)
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
