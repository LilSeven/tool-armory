#!/usr/bin/env python3
r"""同尺寸图片查找器（image-dup-dimension）

用途:
    递归扫描目录中的 PNG/JPEG/GIF 图片，直接解析文件头获取宽高，
    把"分辨率相同"的图片归为一组列出，供人工比对是否为重复图片。
    每个文件只读取开头几十个字节，不做像素级比对，速度极快。

示例命令:
    python image-dup-dimension.py K:\photos
    python image-dup-dimension.py K:\photos --all
    python image-dup-dimension.py K:\photos --json

说明:
    - 按文件签名识别格式（与扩展名无关），但只扫描常见图片扩展名:
      .png/.jpg/.jpeg/.gif（大小写不敏感）。
    - 无法识别文件头的文件单独列在"无法识别"中，不参与分组。
    - JPEG 会扫描段结构寻找 SOF 标记，兼容 baseline 与 progressive。

退出码:
    0 = 正常完成（未找到同尺寸图片也算正常）
    2 = 参数错误或目录不存在
"""

import argparse
import json
import os
import struct
import sys
from collections import defaultdict

IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif"}


def _safe_stdout():
    """控制台编码不支持某些字符时，避免因打印而崩溃。"""
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass


def png_size(fp):
    """从已打开的二进制文件对象解析 PNG 宽高；失败返回 None。"""
    fp.seek(0)
    head = fp.read(24)
    if len(head) < 24:
        return None
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if head[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", head[16:24])
    return width, height


def gif_size(fp):
    """从已打开的二进制文件对象解析 GIF 宽高；失败返回 None。"""
    fp.seek(0)
    head = fp.read(10)
    if len(head) < 10 or head[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    width, height = struct.unpack("<HH", head[6:10])
    return width, height


def jpeg_size(fp):
    """扫描 JPEG 段结构找到 SOF 标记并解析宽高；失败返回 None。"""
    fp.seek(0)
    if fp.read(2) != b"\xff\xd8":
        return None
    while True:
        b1 = fp.read(1)
        if not b1:
            return None  # 文件提前结束
        if b1 != b"\xff":
            continue
        marker_bytes = fp.read(1)
        while marker_bytes == b"\xff":  # 跳过连续填充字节
            marker_bytes = fp.read(1)
        if not marker_bytes:
            return None
        marker = marker_bytes[0]
        if marker == 0x01 or marker == 0xD8 or 0xD0 <= marker <= 0xD7:
            continue  # 无长度字段的独立标记（TEM/SOI/RSTn）
        seg = fp.read(2)
        if len(seg) < 2:
            return None
        (seg_len,) = struct.unpack(">H", seg)
        if seg_len < 2:
            return None
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            payload = fp.read(5)
            if len(payload) < 5:
                return None
            height, width = struct.unpack(">HH", payload[1:5])
            return width, height
        fp.seek(seg_len - 2, 1)  # 跳过本段剩余数据


PARSERS = (png_size, gif_size, jpeg_size)


def scan_images(root):
    """返回 (images, unreadable)。

    images:    [(path, width, height, bytes), ...]
    unreadable:[(path, reason), ...]
    """
    images, unreadable = [], []
    for dirpath, _dirnames, filenames in os.walk(root, onerror=lambda e: None):
        for name in filenames:
            if os.path.splitext(name)[1].lower() not in IMG_EXTS:
                continue
            path = os.path.join(dirpath, name)
            try:
                nbytes = os.path.getsize(path)
                with open(path, "rb") as fp:
                    dims = None
                    for parse in PARSERS:
                        dims = parse(fp)
                        if dims:
                            break
            except OSError as exc:
                unreadable.append((path, "读取失败: %s" % exc))
                continue
            if dims and dims[0] > 0 and dims[1] > 0:
                images.append((path, dims[0], dims[1], nbytes))
            else:
                unreadable.append((path, "不是可识别的 PNG/JPEG/GIF 文件头"))
    return images, unreadable


def fmt_bytes(n):
    return "{:,} B".format(n)


def main(argv=None):
    _safe_stdout()
    parser = argparse.ArgumentParser(
        description="解析 PNG/JPEG/GIF 文件头获取宽高，找出分辨率相同的图片供人工比对重复。")
    parser.add_argument("directory", help="要扫描的目录")
    parser.add_argument("--all", action="store_true",
                        help="除重复组外，也列出只出现一次的分辨率")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)

    root = args.directory
    if not os.path.isdir(root):
        print("错误: 目录不存在或不是目录: %s" % root, file=sys.stderr)
        return 2

    images, unreadable = scan_images(root)
    groups = defaultdict(list)
    for path, w, h, nbytes in images:
        groups[(w, h)].append((path, nbytes))

    dup_groups = [(k, v) for k, v in groups.items() if len(v) > 1]
    dup_groups.sort(key=lambda kv: (-len(kv[1]), kv[0]))
    singles = [(k, v) for k, v in groups.items() if len(v) == 1]
    singles.sort(key=lambda kv: kv[0])

    if args.json:
        payload = {
            "root": os.path.abspath(root),
            "total_images": len(images),
            "duplicate_groups": [
                {"width": w, "height": h, "count": len(files),
                 "files": [{"path": p, "bytes": n} for p, n in sorted(files)]}
                for (w, h), files in dup_groups
            ],
            "single_images": [
                {"width": w, "height": h, "path": p, "bytes": n}
                for (w, h), files in singles for p, n in files
            ],
            "unreadable": [{"path": p, "reason": r} for p, r in unreadable],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("扫描目录: %s" % os.path.abspath(root))
    print("识别到图片 %d 张；同分辨率组 %d 组。" % (len(images), len(dup_groups)))
    if dup_groups:
        print()
        for (w, h), files in dup_groups:
            print("[%dx%d] %d 张:" % (w, h, len(files)))
            for p, n in sorted(files):
                print("  - %s (%s)" % (p, fmt_bytes(n)))
    else:
        print("未发现分辨率相同的图片。")
    if args.all and singles:
        print()
        print("仅出现一次的分辨率（--all）:")
        for (w, h), files in singles:
            p, n = files[0]
            print("  [%dx%d] %s (%s)" % (w, h, p, fmt_bytes(n)))
    if unreadable:
        print()
        print("无法识别的文件 %d 个:" % len(unreadable))
        for p, r in unreadable:
            print("  - %s (%s)" % (p, r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
