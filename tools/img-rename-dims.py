#!/usr/bin/env python3
"""img-rename-dims —— 把图片重命名为 原名-WxH 形式（默认 dry-run 预览）。

解析 JPEG/PNG/GIF/BMP 文件头得到宽高（只用标准库），在原文件名末尾追加
"-宽x高"，例如 IMG_0001.jpg -> IMG_0001-640x480.jpg；文件名已有 -WxH 后缀
时按最新尺寸替换，因此重复运行安全（幂等）。默认只打印预览，加 -x/--exec
才真正执行 os.rename。

用法:
    python img-rename-dims.py <文件或目录>... [-r] [-x]

示例命令:
    python img-rename-dims.py D:/photos            # 预览将要进行的改名
    python img-rename-dims.py D:/photos -x         # 实际执行改名
    python img-rename-dims.py D:/photos -r -x      # 含子目录一起改名

说明:
    * 按文件头签名识别图片，不看扩展名；无法识别的文件计入"非图片/无法识别"。
"""

import argparse
import os
import re
import struct
import sys

DIMS_TAIL = re.compile(r"-(\d+)x(\d+)\s*$")


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


def _jpeg_size(path):
    """顺序扫描 JPEG 段，遇到 SOFn 返回 (宽, 高)。"""
    with open(path, "rb") as f:
        if f.read(2) != b"\xff\xd8":
            return None
        while True:
            byte = f.read(1)
            while byte == b"\xff":  # 跳过填充字节
                byte = f.read(1)
            if len(byte) != 1:
                return None
            marker = byte[0]
            if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
                continue
            if marker in (0xD9, 0xDA):  # EOI/SOS 之后是图像数据
                return None
            header = f.read(2)
            if len(header) < 2:
                return None
            seg_len = struct.unpack(">H", header)[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                body = f.read(5)  # 精度(1) + 高(2) + 宽(2)
                if len(body) < 5:
                    return None
                height, width = struct.unpack(">HH", body[1:5])
                return (width, height) if width and height else None
            if seg_len < 2:
                return None
            f.seek(seg_len - 2, 1)


def _png_size(head):
    if len(head) < 24 or head[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", head[16:24])
    return (width, height) if width and height else None


def _gif_size(head):
    if len(head) < 10:
        return None
    width, height = struct.unpack("<HH", head[6:10])
    return (width, height) if width and height else None


def _bmp_size(head):
    if len(head) < 26:
        return None
    header_size = struct.unpack_from("<I", head, 14)[0]
    if header_size < 40:  # 只处理标准 BITMAPINFOHEADER 及以上
        return None
    width, height = struct.unpack_from("<ii", head, 18)
    return (width, abs(height)) if width > 0 and height != 0 else None


def image_size(path):
    """返回 (宽, 高)；不是 JPEG/PNG/GIF/BMP 或读取失败返回 None。"""
    try:
        with open(path, "rb") as f:
            head = f.read(32)
        if head[:2] == b"\xff\xd8":
            return _jpeg_size(path)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return _png_size(head)
        if head[:6] in (b"GIF87a", b"GIF89a"):
            return _gif_size(head)
        if head[:2] == b"BM":
            return _bmp_size(head)
    except (OSError, struct.error):
        return None
    return None


def target_name(name, width, height):
    stem, ext = os.path.splitext(name)
    stem = DIMS_TAIL.sub("", stem)  # 幂等：替换旧的 -WxH 后缀
    return f"{stem}-{width}x{height}{ext}"


def _safe_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _safe_stdio()
    parser = argparse.ArgumentParser(
        prog="img-rename-dims",
        description="把图片重命名为 原名-WxH 形式（默认 dry-run 预览）。",
    )
    parser.add_argument("paths", nargs="+", help="图片文件或目录")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="递归扫描子目录")
    parser.add_argument("-x", "--exec", dest="do_exec", action="store_true",
                        help="实际执行改名（默认仅预览）")
    args = parser.parse_args(argv)

    done = planned = kept = collided = not_img = 0
    for fp in iter_files(args.paths, args.recursive):
        size = image_size(fp)
        if size is None:
            not_img += 1
            continue
        width, height = size
        base = os.path.basename(fp)
        new = target_name(base, width, height)
        if new == base:
            kept += 1
            continue
        tgt = os.path.join(os.path.dirname(fp), new)
        if os.path.exists(tgt):
            collided += 1
            print(f"[跳过] 目标已存在: {base} -> {new}")
            continue
        if args.do_exec:
            os.rename(fp, tgt)
            print(f"[改名] {base} -> {new}")
            done += 1
        else:
            print(f"[预览] {base} -> {new}")
            planned += 1

    mode = "执行" if args.do_exec else "预览（dry-run）"
    n = done if args.do_exec else planned
    print(f"-- {mode}: 改名 {n} 个，已是目标命名 {kept} 个，目标冲突 {collided} 个，"
          f"非图片/无法识别 {not_img} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
