#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gif-frame-extract-info —— 定位 GIF 指定帧的图像描述符与图形控制扩展。

用途:
    按帧序号 (0 基) 定位 GIF 的第 N 帧, 输出:
      * 图像描述符 (0x2C) 的文件偏移、left/top/width/height、是否隔行、有无局部调色板;
      * 其前方的图形控制扩展 (0x21 0xF9) 的偏移、延时 (1/100 秒)、透明色索引、
        处置方式 (disposal method) 与用户输入标志;
      * 本帧实际使用的调色板: 局部调色板优先, 否则全局调色板, 给出偏移与颜色数。

用法:
    python -I gif-frame-extract-info.py <file.gif> <frame_index> [--json]

示例:
    python -I gif-frame-extract-info.py anim.gif 0
    python -I gif-frame-extract-info.py anim.gif 1 --json

退出码: 0=成功; 1=不是 GIF/结构损坏/帧序号越界; 2=命令行参数错误。
仅使用 Python 标准库。
"""

import argparse
import json
import sys

DISPOSAL_NAMES = {
    0: "unspecified",
    1: "do not dispose",
    2: "restore to background",
    3: "restore to previous",
}


class GifError(Exception):
    """GIF 结构错误。"""


class FrameNotFound(GifError):
    """帧序号越界。"""


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


def parse_gif(data, target):
    """遍历 GIF 块结构, 返回第 target 帧 (0 基) 的描述符/GCE/调色板信息。"""
    n = len(data)
    if n < 13 or data[:3] != b"GIF":
        raise GifError("not a GIF file (bad header)")
    version = data[3:6]
    if version not in (b"87a", b"89a"):
        raise GifError("unknown GIF version %r" % version)
    if target < 0:
        raise GifError("frame index must be >= 0")

    lsd_flags = data[10]
    gct = None
    if lsd_flags & 0x80:
        gct = {"offset": 13, "colors": 2 << (lsd_flags & 0x07)}
    pos = 13 + (3 * gct["colors"] if gct else 0)

    frames = 0
    pending_gce = None
    found = None
    has_trailer = False

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
                p += blen
                _, p = read_subblocks(data, p)
                pos = p
            elif label == 0xF9:                          # Graphic Control Extension
                if p >= n:
                    raise GifError("file truncated in graphic control extension at offset %d" % pos)
                bs = data[p]
                if p + 1 + bs > n:
                    raise GifError("file truncated in graphic control extension at offset %d" % pos)
                if bs >= 4:
                    packed = data[p + 1]
                    pending_gce = {
                        "offset": pos,
                        "delay_cs": data[p + 2] | (data[p + 3] << 8),
                        "disposal_method": (packed >> 2) & 0x07,
                        "user_input": bool(packed & 0x02),
                        "transparent_flag": bool(packed & 0x01),
                        "transparent_index": data[p + 4],
                    }
                _, pos = read_subblocks(data, p + 1 + bs)
            else:                                        # 其他扩展: 跳过其子块
                _, pos = read_subblocks(data, p)
        elif b == 0x2C:                                  # Image Descriptor
            frames += 1
            desc_off = pos
            if pos + 10 > n:
                raise GifError("file truncated in image descriptor at offset %d" % pos)
            left = data[pos + 1] | (data[pos + 2] << 8)
            top = data[pos + 3] | (data[pos + 4] << 8)
            width = data[pos + 5] | (data[pos + 6] << 8)
            height = data[pos + 7] | (data[pos + 8] << 8)
            packed = data[pos + 9]
            lct_flag = bool(packed & 0x80)
            lct_colors = 2 << (packed & 0x07) if lct_flag else 0
            p = pos + 10
            if lct_flag:
                p += 3 * lct_colors
            if p >= n:
                raise GifError("file truncated before LZW data of frame %d" % frames)
            p += 1                                       # LZW minimum code size
            _, pos = read_subblocks(data, p)
            if frames == target + 1 and found is None:
                found = {
                    "frame_index": target,
                    "descriptor_offset": desc_off,
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
                    "interlaced": bool(packed & 0x40),
                    "local_color_table": ({"offset": desc_off + 10, "colors": lct_colors}
                                          if lct_flag else None),
                    "gce": pending_gce,
                }
            pending_gce = None
        elif b == 0x3B:                                  # Trailer
            has_trailer = True
            break
        else:
            raise GifError("unexpected byte 0x%02X at offset %d" % (b, pos))

    if not has_trailer:
        raise GifError("missing GIF trailer (0x3B); file truncated?")
    if found is None:
        raise FrameNotFound("frame index %d out of range (file has %d frame(s))"
                            % (target, frames))

    found["frames_total"] = frames
    found["version"] = "GIF" + version.decode("ascii")
    if found["local_color_table"]:
        found["palette"] = dict(found["local_color_table"], source="local")
    elif gct:
        found["palette"] = dict(gct, source="global")
    else:
        found["palette"] = None
    return found


def human_report(path, size, info):
    lines = [
        "file: %s" % path,
        "size: %d bytes" % size,
        "version: %s" % info["version"],
        "frame_index: %d (0-based) of %d frame(s)"
        % (info["frame_index"], info["frames_total"]),
        "",
        "[image descriptor]",
        "  offset: %d (0x%X)" % (info["descriptor_offset"], info["descriptor_offset"]),
        "  left: %d  top: %d  width: %d  height: %d"
        % (info["left"], info["top"], info["width"], info["height"]),
        "  interlaced: %s" % ("yes" if info["interlaced"] else "no"),
    ]
    lct = info["local_color_table"]
    if lct:
        lines.append("  local_color_table: yes (offset %d (0x%X), %d colors)"
                     % (lct["offset"], lct["offset"], lct["colors"]))
    else:
        lines.append("  local_color_table: no")
    lines.append("")
    lines.append("[graphic control extension]")
    g = info["gce"]
    if g is None:
        lines.append("  none (this frame has no GCE)")
    else:
        lines.append("  offset: %d (0x%X)" % (g["offset"], g["offset"]))
        lines.append("  delay: %d cs (%.2f s)" % (g["delay_cs"], g["delay_cs"] / 100.0))
        disp = g["disposal_method"]
        lines.append("  disposal_method: %d (%s)"
                     % (disp, DISPOSAL_NAMES.get(disp, "reserved")))
        if g["transparent_flag"]:
            lines.append("  transparent_index: %d" % g["transparent_index"])
        else:
            lines.append("  transparent_index: none (transparent flag off)")
        lines.append("  user_input: %s" % ("yes" if g["user_input"] else "no"))
    lines.append("")
    lines.append("[palette in use]")
    pal = info["palette"]
    if pal is None:
        lines.append("  none (no local and no global color table)")
    else:
        lines.append("  source: %s" % pal["source"])
        lines.append("  offset: %d (0x%X)" % (pal["offset"], pal["offset"]))
        lines.append("  colors: %d" % pal["colors"])
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="gif-frame-extract-info",
        description="定位 GIF 指定帧的图像描述符与图形控制扩展, 输出偏移/延时/透明索引/调色板。")
    ap.add_argument("file", help="GIF 文件路径")
    ap.add_argument("index", type=int, help="帧序号 (0 基)")
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
        info = parse_gif(data, args.index)
    except GifError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1

    if args.json:
        out = {"file": args.file, "size": len(data)}
        out.update(info)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(human_report(args.file, len(data), info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
