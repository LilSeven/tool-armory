#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gif-anim-info —— 输出 GIF 动画信息:帧数、每帧延时、循环次数与总播放时长、disposal。

解析 GIF 数据流:帧数来自图像描述符计数;每帧延时与 disposal 方式取自
其前方的图形控制扩展(0x21 0xF9,延时单位为 1/100 秒);循环次数取自
NETSCAPE2.0 应用扩展(0 表示无限循环);总播放时长为各帧延时之和
(一轮循环的时长,无限循环时按轮给出)。缺 GCE 的帧延时按 0、disposal
按无处理。仅用 Python 标准库。

用法:
    python gif-anim-info.py FILE

示例:
    python gif-anim-info.py anim.gif
    python gif-anim-info.py "K:/tmp/表情包.gif"

退出码: 0 解析成功;1 文件不是 GIF、损坏或被截断;2 参数错误。
"""

import argparse
import struct
import sys

TRAILER = 0x3B
IMAGE_SEP = 0x2C
EXTENSION = 0x21
LABEL_GRAPHIC_CONTROL = 0xF9
LABEL_APPLICATION = 0xFF

DISPOSAL_NAMES = {
    0: "unspecified(0)",
    1: "do not dispose(1)",
    2: "restore to background(2)",
    3: "restore to previous(3)",
}


class GIFError(Exception):
    """输入不是合法的 GIF 数据流。"""


def setup_stdio():
    """Windows 管道/重定向下强制 UTF-8 输出,避免 GBK 编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", newline="\n")
        except (AttributeError, ValueError):
            pass


def disposal_name(code):
    return DISPOSAL_NAMES.get(code, "undefined(%d)" % code)


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
    """解析 GIF 字节流,返回 (info, blocks, trailing)。"""
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


def collect_frames(blocks):
    """把图像描述符与其前方生效的图形控制扩展配对,返回帧列表。"""
    frames = []
    pending = None
    for blk in blocks:
        if blk["kind"] == "extension" and blk["label"] == LABEL_GRAPHIC_CONTROL:
            p = blk["payload"]
            pending = None
            if len(p) >= 4:
                pending = {
                    "delay": struct.unpack_from("<H", p, 1)[0],
                    "disposal": (p[0] >> 2) & 0x07,
                    "transparent": p[3] if p[0] & 0x01 else None,
                }
        elif blk["kind"] == "image":
            frames.append({"image": blk, "gce": pending})
            pending = None
    return frames


def find_loop_count(blocks):
    """从 NETSCAPE2.0 应用扩展取循环次数;没有则返回 None。"""
    for blk in blocks:
        if blk["kind"] == "extension" and blk.get("app_id") == b"NETSCAPE2.0":
            p = blk.get("payload", b"")
            if len(p) >= 3 and p[0] == 1:
                return struct.unpack_from("<H", p, 1)[0]
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="输出 GIF 动画信息:帧数、每帧延时、循环次数、总播放时长与 disposal 方式。")
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
        info, blocks, _trailing = parse_stream(data)
    except GIFError as exc:
        print("错误:%s" % exc, file=sys.stderr)
        return 1

    frames = collect_frames(blocks)
    loop = find_loop_count(blocks)
    total_units = sum(f["gce"]["delay"] for f in frames if f["gce"])
    total_ms = total_units * 10

    print("version: %s" % info["version"])
    print("canvas: %dx%d" % (info["screen_width"], info["screen_height"]))
    print("frames: %d" % len(frames))
    if loop is None:
        print("loop: 未找到 NETSCAPE2.0 扩展 (按单次播放处理)")
    else:
        print("loop: %d%s" % (loop, " (0 = 无限循环)" if loop == 0 else ""))
    print("cycle duration: %d ms (共 %d 个 1/100s 延时单位)" % (total_ms, total_units))
    if loop is None:
        print("total duration: %d ms (单次播放)" % total_ms)
    elif loop == 0:
        print("total duration: 无限循环, 每轮 %d ms" % total_ms)
    else:
        print("total duration: 约 %d ms (%d 轮 × %d ms)" % (loop * total_ms, loop, total_ms))
    print()
    if not frames:
        print("(该 GIF 不含任何帧)")
        return 0

    print("%5s %13s %10s  %-24s %s" % ("frame", "delay(1/100s)", "delay(ms)", "disposal", "transparent"))
    for i, frame in enumerate(frames):
        gce = frame["gce"]
        if gce:
            delay_units = gce["delay"]
            disp = disposal_name(gce["disposal"])
            transp = ("yes (index %d)" % gce["transparent"]) if gce["transparent"] is not None else "no"
        else:
            delay_units, disp, transp = 0, "-", "-"
        print("%5d %13d %10d  %-24s %s" % (i, delay_units, delay_units * 10, disp, transp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
