#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG 调色板转储 —— 解析 PLTE 块, 输出颜色数与前 N 项 RGB 并检测异常。

输出 PLTE 块的颜色数量与前 N 项的 RGB 值(#RRGGBB 与 (r, g, b) 形式);
检测重复色(相同 RGB 多次出现, 仅提示、不影响退出码)与超界项:
  - PLTE 长度不是 3 的倍数(尾部字节无法构成完整颜色项);
  - 颜色项数超过 PNG 上限 256;
  - 颜色类型 3 时项数超过 IHDR 位深允许的 2^bit_depth 上限。
单个颜色项的 R/G/B 本身是字节, 不可能超过 255, 故"超界"按项数上限判定。

用法:
    python png-plte-dump.py <文件.png> [--num N] [--all]

参数:
    --num N   只列出前 N 项(默认 16)
    --all     列出全部颜色项

退出码:
    0 = 找到 PLTE 且结构正常(重复色只作提示)
    1 = 未找到 PLTE(颜色类型非 3 时通常属正常), 或 PLTE 超界/长度异常
    2 = 文件不存在、无法读取, 或 PNG 签名不符

示例:
    python png-plte-dump.py icon.png --num 8
    python png-plte-dump.py sprite.png --all

仅使用 Python 标准库, 需 Python 3.7+。
"""

import argparse
import collections
import struct
import sys
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"

CT_NAMES = {0: "灰度", 2: "真彩 RGB", 3: "索引色", 4: "灰度+Alpha", 6: "真彩+Alpha"}


def setup_stdio():
    """Windows 控制台/管道下强制 UTF-8 输出, 避免中文乱码或崩溃。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_chunks(blob):
    """解析 PNG 块流, 在 IEND 块之后或结构异常处停止。

    返回 (chunks, stop_offset, problem):
      chunks      -> [(offset, type_bytes, payload, crc_ok)]
                     offset 为块长度字段的起始偏移, crc_ok 为 CRC 是否匹配;
      stop_offset -> 解析停止位置(干净文件应等于 len(blob));
      problem     -> None 或结构异常描述字符串。
    """
    chunks = []
    problem = None
    pos = 8
    n = len(blob)
    stopped_at_iend = False
    while pos + 8 <= n:
        (length,) = struct.unpack(">I", blob[pos:pos + 4])
        ctype = blob[pos + 4:pos + 8]
        end = pos + 12 + length
        if end > n:
            problem = ("偏移 %d 的 %s 块声明 %d 字节数据, 超出文件末尾(缺 %d 字节)"
                       % (pos, ctype.decode("latin-1"), length, end - n))
            break
        payload = blob[pos + 8:pos + 8 + length]
        (crc_stored,) = struct.unpack(">I", blob[end - 4:end])
        crc_ok = (zlib.crc32(ctype + payload) & 0xFFFFFFFF) == crc_stored
        chunks.append((pos, ctype, payload, crc_ok))
        pos = end
        if ctype == b"IEND":
            stopped_at_iend = True
            break
    if problem is None and not stopped_at_iend and pos < n:
        problem = "偏移 %d 起剩余 %d 字节, 不足以构成完整块" % (pos, n - pos)
    return chunks, pos, problem


def read_ihdr(chunks):
    """读取首个块的 IHDR 字段; 失败返回 None。"""
    if not chunks or chunks[0][1] != b"IHDR":
        return None
    payload = chunks[0][2]
    if len(payload) != 13:
        return None
    width, height, bd, ct, comp, filt, inter = struct.unpack(">IIBBBBB", payload)
    return {"width": width, "height": height, "bit_depth": bd, "color_type": ct,
            "compression": comp, "filter_method": filt, "interlace": inter}


def main(argv=None):
    setup_stdio()
    ap = argparse.ArgumentParser(
        description="转储 PNG PLTE 调色板: 颜色数与前 N 项 RGB, 检测重复色与超界项")
    ap.add_argument("file", help="PNG 文件路径")
    ap.add_argument("--num", type=int, default=16, help="列出的前 N 项(默认 16)")
    ap.add_argument("--all", action="store_true", help="列出全部颜色项")
    args = ap.parse_args(argv)

    try:
        with open(args.file, "rb") as fh:
            blob = fh.read()
    except OSError as exc:
        print("错误: 无法读取文件: %s" % exc, file=sys.stderr)
        return 2
    if not blob.startswith(SIGNATURE):
        print("错误: PNG 签名不符, 不是有效的 PNG 文件", file=sys.stderr)
        return 2

    chunks, _stop, problem = parse_chunks(blob)
    if problem:
        print("警告: %s" % problem)

    pltes = [c for c in chunks if c[1] == b"PLTE"]
    if len(pltes) > 1:
        print("警告: 发现 %d 个 PLTE 块(规范只允许 1 个), 分析第 1 个" % len(pltes))
    if not pltes:
        ihdr = read_ihdr(chunks)
        hint = ""
        if ihdr is not None:
            ct = ihdr["color_type"]
            if ct == 3:
                hint = "; 颜色类型 3(索引色)缺少 PLTE 属于严重问题"
            elif ct in CT_NAMES:
                hint = "; 颜色类型 %d(%s)本就不需要调色板, 属正常现象" % (ct, CT_NAMES[ct])
        print("未找到 PLTE 块%s (退出码 1)" % hint)
        return 1

    off, _ctype, payload, crc_ok = pltes[0]
    if not crc_ok:
        print("警告: PLTE 块 CRC 校验失败")

    length = len(payload)
    leftover = length % 3
    entries = [tuple(payload[i:i + 3]) for i in range(0, length - leftover, 3)]
    count = len(entries)

    ihdr = read_ihdr(chunks)
    limit = 256
    ctx = "(无 IHDR 上下文)"
    if ihdr is not None:
        ct, bd = ihdr["color_type"], ihdr["bit_depth"]
        limit = 2 ** bd if ct == 3 and bd in (1, 2, 4, 8) else 256
        ctx = "颜色类型 %d (%s), 位深 %d" % (ct, CT_NAMES.get(ct, "未定义"), bd)

    print("PLTE 块: 偏移 %d, 数据 %d 字节, %d 个颜色项" % (off, length, count))
    print("IHDR 上下文: %s -> 项数上限 %d" % (ctx, limit))

    show = count if args.all else max(0, min(args.num, count))
    if show:
        print("前 %d 项:" % show)
        for i in range(show):
            r, g, b = entries[i]
            print("  [%3d] #%02X%02X%02X  (%3d, %3d, %3d)" % (i, r, g, b, r, g, b))

    freq = collections.Counter(entries)
    dups = [(rgb, n) for rgb, n in freq.items() if n > 1]
    if dups:
        extra = sum(n - 1 for _rgb, n in dups)
        print("重复色: %d 种颜色重复出现, 共多占 %d 项(仅提示)" % (len(dups), extra))
        for rgb, n in sorted(dups, key=lambda kv: -kv[1])[:10]:
            idxs = [i for i, e in enumerate(entries) if e == rgb]
            shown = ", ".join(map(str, idxs[:6])) + (", ..." if len(idxs) > 6 else "")
            print("  #%02X%02X%02X 出现 %d 次 (索引 %s)" % (rgb[0], rgb[1], rgb[2], n, shown))
    else:
        print("重复色: 无")

    problems = []
    if leftover:
        problems.append("PLTE 长度 %d 不是 3 的倍数, 末尾 %d 字节无法构成完整颜色项"
                        % (length, leftover))
    if count > 256:
        problems.append("颜色项数 %d 超过 PNG 规范上限 256" % count)
    elif ihdr is not None and ihdr["color_type"] == 3 and count > limit:
        problems.append("颜色项数 %d 超过 IHDR 位深 %d 允许的上限 %d (2^%d)"
                        % (count, ihdr["bit_depth"], limit, ihdr["bit_depth"]))

    if problems:
        for p in problems:
            print("异常: %s" % p)
        print("结果: PLTE 存在结构异常 (退出码 1)")
        return 1
    print("超界检查: 项数 %d <= 上限 %d; 长度 %d = 3 x %d 项, 均正常" % (count, limit, length, count))
    print("结果: PLTE 结构正常 (退出码 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
