#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG 颜色类型解释 —— 解释颜色类型与位深组合的通道数/Alpha/每像素位数。

给定颜色类型(color type)与位深(bit depth), 输出对应通道数、是否含
Alpha 通道、每像素位数与每像素字节数, 并判定该组合是否符合 PNG 规范;
也可直接读取 PNG 文件的 IHDR 解释其实际组合, 或用 --table 列出全部
合法组合。颜色类型 1、5 未在规范中定义, 属非法值。

用法:
    python png-color-type-explain.py <文件.png>
    python png-color-type-explain.py --color-type 6 --bit-depth 8
    python png-color-type-explain.py --table

退出码:
    0 = 解释成功且组合合法
    1 = 组合非法(颜色类型为未定义的 1/5, 或位深不被该颜色类型允许)
    2 = 用法错误、文件不存在/无法读取、PNG 签名不符或 IHDR 缺失

示例:
    python png-color-type-explain.py photo.png
    python png-color-type-explain.py --color-type 3 --bit-depth 4
    python png-color-type-explain.py --table

仅使用 Python 标准库, 需 Python 3.7+。
"""

import argparse
import struct
import sys
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"

# 颜色类型 -> (名称, 允许位深, 通道数, 是否含 Alpha, 备注)
CT_INFO = {
    0: ("灰度 grayscale", (1, 2, 4, 8, 16), 1, False,
        "每像素 1 个灰度样本"),
    2: ("真彩 RGB truecolor", (8, 16), 3, False,
        "R/G/B 三个样本, 透明可由 tRNS 辅助实现"),
    3: ("索引色 indexed-color", (1, 2, 4, 8), 1, False,
        "样本为 PLTE 调色板索引, 透明由 tRNS 提供"),
    4: ("灰度+Alpha grayscale+alpha", (8, 16), 2, True,
        "灰度与 Alpha 两个样本"),
    6: ("真彩+Alpha truecolor+alpha", (8, 16), 4, True,
        "R/G/B/A 四个样本"),
}


def setup_stdio():
    """Windows 控制台/管道下强制 UTF-8 输出, 避免中文乱码或崩溃。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_chunks(blob):
    """解析 PNG 块流, 在 IEND 块之后或结构异常处停止。

    返回 (chunks, stop_offset, problem), chunk 为
    (offset, type_bytes, payload, crc_ok), offset 指块长度字段起始偏移。
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


def explain(ct, bd):
    """打印解释, 返回组合是否合法。"""
    info = CT_INFO.get(ct)
    if info is None:
        print("颜色类型 %d: 未在 PNG 规范中定义(合法值仅 0/2/3/4/6, 1 和 5 为非法保留值)"
              % ct)
        print("结论: 非法颜色类型 (退出码 1)")
        return False
    name, allowed, channels, has_alpha, note = info
    bpp = channels * bd
    alpha_txt = "是" if has_alpha else ("否(可用 tRNS 提供透明)" if ct in (0, 2, 3) else "否")
    print("颜色类型:   %d (%s)" % (ct, name))
    print("位深:       %d 位/样本" % bd)
    print("允许位深:   %s" % ", ".join(map(str, allowed)))
    print("通道数:     %d" % channels)
    print("含 Alpha:   %s" % alpha_txt)
    print("每像素位数: %d 位 (%d 通道 x %d 位)" % (bpp, channels, bd))
    if bpp % 8 == 0:
        print("每像素字节: %d 字节" % (bpp // 8))
    else:
        print("每像素字节: %g 字节(按位打包, 行尾补齐到字节)" % (bpp / 8))
    if note:
        print("说明:       %s" % note)
    if bd in allowed:
        print("结论:       合法组合 (退出码 0)")
        return True
    print("结论:       非法组合 —— 颜色类型 %d 仅允许位深 %s (退出码 1)"
          % (ct, "/".join(map(str, allowed))))
    return False


def explain_file(path):
    """读取 PNG 的 IHDR 并解释其颜色类型/位深组合。返回退出码。"""
    try:
        with open(path, "rb") as fh:
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
    if not chunks or chunks[0][1] != b"IHDR" or len(chunks[0][2]) != 13:
        print("错误: 未找到合法的 IHDR 块", file=sys.stderr)
        return 2
    w, h, bd, ct, _comp, _filt, inter = struct.unpack(">IIBBBBB", chunks[0][2])
    inter_txt = {0: "无隔行", 1: "Adam7 隔行"}.get(inter, "未知(%d)" % inter)
    print("文件: %s (%d 字节)" % (path, len(blob)))
    print("IHDR: %dx%d, 颜色类型 %d, 位深 %d, %s" % (w, h, ct, bd, inter_txt))
    print("-" * 48)
    return 0 if explain(ct, bd) else 1


def print_table():
    """列出全部合法的颜色类型 x 位深组合。"""
    print("%-4s %-30s %-14s %-8s %s" % ("CT", "名称", "允许位深", "含Alpha", "每像素位数"))
    print("-" * 78)
    for ct in sorted(CT_INFO):
        name, allowed, ch, alpha, _note = CT_INFO[ct]
        print("%-4d %-30s %-14s %-8s %s"
              % (ct, name, ",".join(map(str, allowed)),
                 "是" if alpha else "否", "/".join(str(ch * b) for b in allowed)))
    print("注: 颜色类型 1、5 未在规范中定义; 索引色的透明由 tRNS 提供。")


def main(argv=None):
    setup_stdio()
    ap = argparse.ArgumentParser(
        description="解释 PNG 颜色类型与位深组合: 通道数/是否含 Alpha/每像素位数")
    ap.add_argument("file", nargs="?",
                    help="PNG 文件路径(或用 --color-type/--bit-depth 直接指定组合)")
    ap.add_argument("--color-type", type=int, help="颜色类型 0/2/3/4/6")
    ap.add_argument("--bit-depth", type=int, help="位深 1/2/4/8/16")
    ap.add_argument("--table", action="store_true", help="列出全部合法组合")
    args = ap.parse_args(argv)

    if args.table:
        print_table()
        return 0
    if args.file is not None:
        if args.color_type is not None or args.bit_depth is not None:
            print("错误: 文件参数与 --color-type/--bit-depth 不要同时给出", file=sys.stderr)
            return 2
        return explain_file(args.file)
    if args.color_type is not None and args.bit_depth is not None:
        return 0 if explain(args.color_type, args.bit_depth) else 1
    print("错误: 请提供 PNG 文件, 或同时给出 --color-type 与 --bit-depth, 或使用 --table",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
