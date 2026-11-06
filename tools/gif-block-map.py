#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gif-block-map —— 按顺序列出 GIF 数据流中每个块的偏移、大小与摘要。

GIF 文件由 header、逻辑屏幕描述符、可选全局调色板和一串数据块组成。
本工具自上而下扫描整个数据流,按出现顺序打印每个块的十六进制偏移与
字节大小:全局调色板、扩展块(图形控制 0xF9 / 注释 0xFE / 纯文本 0x01 /
应用 0xFF / 未知)、图像描述符(帧,含局部调色板与 LZW 数据大小)以及
trailer,末尾给出块统计。适合手工分析 GIF 结构或在十六进制编辑器中
定位数据块。仅用 Python 标准库。

用法:
    python gif-block-map.py FILE

示例:
    python gif-block-map.py anim.gif
    python gif-block-map.py "K:/tmp/示例动画.gif"

退出码: 0 解析成功;1 文件不是 GIF、损坏或被截断;2 参数错误。
"""

import argparse
import struct
import sys

TRAILER = 0x3B
IMAGE_SEP = 0x2C
EXTENSION = 0x21
LABEL_GRAPHIC_CONTROL = 0xF9
LABEL_COMMENT = 0xFE
LABEL_PLAIN_TEXT = 0x01
LABEL_APPLICATION = 0xFF


class GIFError(Exception):
    """输入不是合法的 GIF 数据流。"""


def setup_stdio():
    """Windows 管道/重定向下强制 UTF-8 输出,避免 GBK 编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", newline="\n")
        except (AttributeError, ValueError):
            pass


def read_sub_blocks(data, pos):
    """读取 pos 处的一串数据子块(长度前缀块,0 为结束),返回 (拼接字节, 结束偏移)。"""
    total = len(data)
    chunks = []
    while True:
        if pos >= total:
            raise GIFError("文件在偏移 %d 处被截断:缺少子块结束符" % pos)
        size = data[pos]
        pos += 1
        if size == 0:
            return b"".join(chunks), pos
        if pos + size > total:
            raise GIFError("文件被截断:偏移 %d 处的 %d 字节子块越过文件尾" % (pos, size))
        chunks.append(data[pos:pos + size])
        pos += size


def parse_stream(data):
    """解析 GIF 字节流,返回 (info, blocks, trailing)。

    info   —— 头部信息字典;
    blocks —— 按流顺序排列的块字典列表(每项含 kind/offset/size);
    trailing —— trailer 之后的剩余字节数。
    """
    if len(data) < 13:
        raise GIFError("文件只有 %d 字节,不可能是 GIF(头部+逻辑屏幕描述符需 13 字节)" % len(data))
    version = bytes(data[:6])
    if version not in (b"GIF87a", b"GIF89a"):
        raise GIFError("不是 GIF 文件(版本字段=%r,应为 GIF87a/GIF89a)" % version)
    sw, sh, packed, bg_index, _aspect = struct.unpack_from("<HHBBB", data, 6)
    gct_flag = bool(packed & 0x80)
    gct_entries = 2 ** ((packed & 0x07) + 1) if gct_flag else 0
    info = {
        "version": version.decode("ascii"),
        "screen_width": sw,
        "screen_height": sh,
        "bg_index": bg_index,
        "gct_flag": gct_flag,
        "gct_entries": gct_entries,
        "gct_raw": b"",
    }
    blocks = []
    pos = 13
    if gct_flag:
        length = gct_entries * 3
        if pos + length > len(data):
            raise GIFError("全局调色板在偏移 %d 处被截断" % pos)
        blocks.append({"kind": "gct", "offset": pos, "size": length,
                       "entries": gct_entries, "raw": bytes(data[pos:pos + length])})
        info["gct_raw"] = blocks[-1]["raw"]
        pos += length
    frame_no = 0
    while True:
        if pos >= len(data):
            raise GIFError("文件在偏移 %d 处结束,缺少 trailer(0x3B)" % pos)
        marker = data[pos]
        if marker == TRAILER:
            blocks.append({"kind": "trailer", "offset": pos, "size": 1})
            pos += 1
            break
        if marker == IMAGE_SEP:
            if pos + 10 > len(data):
                raise GIFError("图像描述符在偏移 %d 处被截断" % pos)
            left, top, width, height, ipacked = struct.unpack_from("<HHHHB", data, pos + 1)
            blk = {
                "kind": "image", "offset": pos, "index": frame_no,
                "left": left, "top": top, "width": width, "height": height,
                "interlace": bool(ipacked & 0x40),
                "lct_entries": 0, "lct_offset": None, "lct_raw": b"",
                "lzw_min_code_size": None, "data_size": 0,
            }
            end = pos + 10
            if ipacked & 0x80:
                lct_entries = 2 ** ((ipacked & 0x07) + 1)
                if end + lct_entries * 3 > len(data):
                    raise GIFError("帧 #%d 的局部调色板在偏移 %d 处被截断" % (frame_no, end))
                blk["lct_entries"] = lct_entries
                blk["lct_offset"] = end
                blk["lct_raw"] = bytes(data[end:end + lct_entries * 3])
                end += lct_entries * 3
            if end >= len(data):
                raise GIFError("帧 #%d 的图像数据在偏移 %d 处被截断" % (frame_no, end))
            blk["lzw_min_code_size"] = data[end]
            data_start = end + 1
            _payload, end = read_sub_blocks(data, data_start)
            blk["data_size"] = end - data_start
            blk["size"] = end - pos
            blocks.append(blk)
            frame_no += 1
            pos = end
        elif marker == EXTENSION:
            if pos + 2 > len(data):
                raise GIFError("扩展块在偏移 %d 处被截断" % pos)
            label = data[pos + 1]
            blk = {"kind": "extension", "offset": pos, "label": label,
                   "size": 0, "payload": b"", "app_id": b""}
            if label == LABEL_APPLICATION:
                if pos + 3 > len(data):
                    raise GIFError("应用扩展在偏移 %d 处被截断" % pos)
                app_size = data[pos + 2]
                if pos + 3 + app_size > len(data):
                    raise GIFError("应用扩展在偏移 %d 处被截断" % pos)
                blk["app_id"] = bytes(data[pos + 3:pos + 3 + app_size])
                payload, end = read_sub_blocks(data, pos + 3 + app_size)
            else:
                payload, end = read_sub_blocks(data, pos + 2)
            blk["payload"] = payload
            blk["size"] = end - pos
            blocks.append(blk)
            pos = end
        else:
            raise GIFError("偏移 %d 处出现无法识别的块标记 0x%02X" % (pos, marker))
    return info, blocks, len(data) - pos


def describe_extension(blk):
    label = blk["label"]
    if label == LABEL_GRAPHIC_CONTROL:
        p = blk["payload"]
        if len(p) < 4:
            return "graphic control extension (畸形,负载 %d 字节)" % len(p)
        delay = struct.unpack_from("<H", p, 1)[0]
        disposal = (p[0] >> 2) & 0x07
        text = "graphic control extension (延时 %d/100s, disposal %d" % (delay, disposal)
        if p[0] & 0x01:
            text += ", 透明索引 %d" % p[3]
        return text + ")"
    if label == LABEL_COMMENT:
        return "comment extension (%d 字节文本)" % len(blk["payload"])
    if label == LABEL_PLAIN_TEXT:
        return "plain text extension (负载 %d 字节)" % len(blk["payload"])
    if label == LABEL_APPLICATION:
        try:
            shown = blk["app_id"].decode("ascii")
        except UnicodeDecodeError:
            shown = blk["app_id"].hex()
        extra = ""
        if (blk["app_id"] == b"NETSCAPE2.0" and len(blk["payload"]) >= 3
                and blk["payload"][0] == 1):
            loop = struct.unpack_from("<H", blk["payload"], 1)[0]
            extra = ", 循环 %d 次%s" % (loop, "(0=无限)" if loop == 0 else "")
        return "application extension %r (负载 %d 字节%s)" % (shown, len(blk["payload"]), extra)
    return "未知扩展 0x%02X (负载 %d 字节)" % (label, len(blk["payload"]))


def describe_image(blk, info):
    text = "image descriptor #%d (%dx%d @ (%d,%d)" % (
        blk["index"], blk["width"], blk["height"], blk["left"], blk["top"])
    if blk["lct_entries"]:
        text += ", 局部调色板 %d 项" % blk["lct_entries"]
    elif info["gct_flag"]:
        text += ", 使用全局调色板"
    else:
        text += ", 无调色板"
    if blk["interlace"]:
        text += ", 交织存放"
    text += ", LZW 最小码长 %d, 图像数据 %d 字节)" % (blk["lzw_min_code_size"], blk["data_size"])
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="按顺序列出 GIF 数据流中各块(图像描述符、扩展块、trailer 等)的偏移与大小。")
    parser.add_argument("file", help="GIF 文件路径")
    args = parser.parse_args(argv)

    setup_stdio()
    try:
        with open(args.file, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        print("错误:无法读取 %s: %s" % (args.file, exc), file=sys.stderr)
        return 1
    try:
        info, blocks, trailing = parse_stream(data)
    except GIFError as exc:
        print("错误:%s" % exc, file=sys.stderr)
        return 1

    print("%s  画布 %dx%d" % (info["version"], info["screen_width"], info["screen_height"]))
    print()
    print("%-8s %8s  %s" % ("offset", "size", "block"))
    for blk in blocks:
        if blk["kind"] == "gct":
            text = "global color table (%d 项)" % blk["entries"]
        elif blk["kind"] == "trailer":
            text = "trailer (0x3B)"
        elif blk["kind"] == "image":
            text = describe_image(blk, info)
        else:
            text = describe_extension(blk)
        print("0x%06X %8d  %s" % (blk["offset"], blk["size"], text))
    if trailing:
        print()
        print("警告:trailer 之后还有 %d 个多余字节" % trailing)
    frames = sum(1 for b in blocks if b["kind"] == "image")
    exts = sum(1 for b in blocks if b["kind"] == "extension")
    print()
    print("共 %d 块:%d 帧 / %d 个扩展块;文件共 %d 字节。" % (len(blocks), frames, exts, len(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
