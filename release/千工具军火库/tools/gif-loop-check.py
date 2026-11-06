#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gif-loop-check —— 检查 GIF 的 NETSCAPE 应用扩展, 报告是否无限循环及循环次数。

用途:
    解析 GIF 文件的块结构, 定位应用扩展 (0x21 0xFF) 中签名为 "NETSCAPE2.0"
    的循环控制块, 读取其中 2 字节小端的循环次数字段:
      * 未找到 NETSCAPE 扩展 -> 不循环, 整段动画只播放一遍;
      * 循环次数 == 0        -> 无限循环;
      * 循环次数 == N (N>0)  -> 首次播放后再额外重复 N 次 (按标准原样报告)。
    顺带报告帧数 (图像描述符个数) 与全局调色板位置, 便于核对文件结构。

用法:
    python -I gif-loop-check.py <file.gif> [--json]

示例:
    python -I gif-loop-check.py anim.gif
    python -I gif-loop-check.py anim.gif --json

退出码: 0=成功; 1=不是 GIF 或结构损坏/截断; 2=命令行参数错误。
仅使用 Python 标准库。
"""

import argparse
import json
import struct
import sys


class GifError(Exception):
    """GIF 结构错误。"""


def read_subblocks(data, p):
    """从 p 起读取一串数据子块 (以 0x00 终止符结束), 返回 (拼接内容, 新位置)。"""
    n = len(data)
    out = bytearray()
    while True:
        if p >= n:
            raise GifError("file truncated inside data sub-blocks at offset %d" % p)
        size = data[p]
        p += 1
        if size == 0:
            return bytes(out), p
        if p + size > n:
            raise GifError("file truncated inside data sub-block at offset %d" % p)
        out += data[p:p + size]
        p += size


def parse_gif(data):
    """遍历 GIF 块结构, 返回概要 dict (含 NETSCAPE 循环信息)。"""
    n = len(data)
    if n < 13 or data[:3] != b"GIF":
        raise GifError("not a GIF file (bad header)")
    version = data[3:6]
    if version not in (b"87a", b"89a"):
        raise GifError("unknown GIF version %r" % version)

    lsd_flags = data[10]
    pos = 13
    gct = None
    if lsd_flags & 0x80:
        colors = 2 << (lsd_flags & 0x07)
        gct = {"offset": 13, "colors": colors}
        pos += 3 * colors

    frames = 0
    loop_count = None        # None 表示未找到 NETSCAPE 扩展
    loop_offset = None
    app_signature = None
    trailer_offset = None

    while pos < n:
        b = data[pos]
        if b == 0x21:                                    # Extension Introducer
            if pos + 2 > n:
                raise GifError("file truncated in extension at offset %d" % pos)
            label = data[pos + 1]
            p = pos + 2
            if label == 0xFF:                            # Application Extension
                if p >= n:
                    raise GifError("file truncated in application extension at offset %d" % pos)
                blen = data[p]
                p += 1
                if p + blen > n:
                    raise GifError("file truncated in application extension header at offset %d" % pos)
                app = data[p:p + blen]
                p += blen
                payload, p = read_subblocks(data, p)
                if app[:8].upper() == b"NETSCAPE" and payload[:1] == b"\x01":
                    if len(payload) < 3:
                        raise GifError("NETSCAPE extension payload too short at offset %d" % pos)
                    loop_count = struct.unpack("<H", payload[1:3])[0]
                    loop_offset = pos
                    app_signature = app.decode("ascii", "replace")
                pos = p
            elif label == 0xF9:                          # Graphic Control Extension
                if p >= n:
                    raise GifError("file truncated in graphic control extension at offset %d" % pos)
                _, pos = read_subblocks(data, p + 1 + data[p])
            else:                                        # 其他扩展: 跳过其子块
                _, pos = read_subblocks(data, p)
        elif b == 0x2C:                                  # Image Descriptor
            frames += 1
            if pos + 10 > n:
                raise GifError("file truncated in image descriptor at offset %d" % pos)
            packed = data[pos + 9]
            p = pos + 10
            if packed & 0x80:                            # 局部调色板
                p += 3 * (2 << (packed & 0x07))
            if p >= n:
                raise GifError("file truncated before LZW data of frame %d" % frames)
            p += 1                                       # LZW minimum code size
            _, pos = read_subblocks(data, p)
        elif b == 0x3B:                                  # Trailer
            trailer_offset = pos
            break
        else:
            raise GifError("unexpected byte 0x%02X at offset %d" % (b, pos))

    if trailer_offset is None:
        raise GifError("missing GIF trailer (0x3B); file truncated?")

    return {
        "version": "GIF" + version.decode("ascii"),
        "frames": frames,
        "global_color_table": gct,
        "netscape_found": loop_count is not None,
        "netscape_offset": loop_offset,
        "netscape_signature": app_signature,
        "loop_count": loop_count,
        "trailer_offset": trailer_offset,
    }


def human_report(path, size, info):
    lines = [
        "file: %s" % path,
        "size: %d bytes" % size,
        "version: %s" % info["version"],
        "frames (image descriptors): %d" % info["frames"],
    ]
    g = info["global_color_table"]
    if g:
        lines.append("global_color_table: offset %d (0x%X), %d colors"
                     % (g["offset"], g["offset"], g["colors"]))
    else:
        lines.append("global_color_table: none")
    if info["netscape_found"]:
        off = info["netscape_offset"]
        lines.append("netscape_loop_extension: yes (offset %d / 0x%X, signature %r)"
                     % (off, off, info["netscape_signature"]))
        lines.append("loop_count: %d" % info["loop_count"])
        if info["loop_count"] == 0:
            lines.append("infinite_loop: yes (loop_count == 0 -> plays forever)")
        else:
            lines.append("infinite_loop: no (plays once, then repeats %d extra time(s))"
                         % info["loop_count"])
    else:
        lines.append("netscape_loop_extension: no")
        lines.append("loop_count: n/a")
        lines.append("infinite_loop: no (no NETSCAPE extension -> plays once)")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="gif-loop-check",
        description="检查 GIF 的 NETSCAPE 应用扩展, 报告是否无限循环及循环次数。")
    ap.add_argument("file", help="GIF 文件路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    try:
        with open(args.file, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        print("error: cannot read %s: %s" % (args.file, exc), file=sys.stderr)
        return 1
    try:
        info = parse_gif(data)
    except GifError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1

    if args.json:
        out = {"file": args.file, "size": len(data)}
        out.update(info)
        out["infinite_loop"] = bool(info["netscape_found"] and info["loop_count"] == 0)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(human_report(args.file, len(data), info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
