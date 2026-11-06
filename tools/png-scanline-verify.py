#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG 行宽验证 —— 按公式计算扫描线总字节数, 与 IDAT 解压长度比对验证完整性。

依据 IHDR 的宽、高、颜色类型、位深与隔行方式, 按 PNG 规范公式计算图像
数据期望字节数: 每个扫描行 = 1 字节滤波类型 + ceil(行宽 x 每像素位数 / 8)
字节像素数据; Adam7 隔行时按 7 个子图逐趟累加。将全部 IDAT 块拼接后用
zlib 解压, 把实际解压长度与期望值比对以验证图像数据完整性; 长度一致时
再走查每行首字节的滤波类型取值是否在 0..4 范围内。

用法:
    python png-scanline-verify.py <文件.png>

退出码:
    0 = 实际长度与公式一致
    1 = 长度不一致, 或 IDAT 解压失败(数据截断/损坏)
    2 = 文件不存在、签名不符、IHDR 缺失/组合非法, 或没有任何 IDAT

示例:
    python png-scanline-verify.py photo.png
    python png-scanline-verify.py interlaced.png

仅使用 Python 标准库, 需 Python 3.7+。
"""

import argparse
import struct
import sys
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"

CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
ALLOWED_BD = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8),
              4: (8, 16), 6: (8, 16)}
CT_NAMES = {0: "灰度", 2: "真彩 RGB", 3: "索引色", 4: "灰度+Alpha", 6: "真彩+Alpha"}
# Adam7 各趟 (x 起点, y 起点, x 步进, y 步进)
ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 8, 4), (2, 0, 4, 4),
         (0, 2, 4, 2), (1, 0, 2, 2), (0, 1, 2, 1))


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


def pass_dims(width, height):
    """计算 Adam7 各趟的 (宽, 高), 空趟为 (0, 0)。"""
    dims = []
    for x0, y0, dx, dy in ADAM7:
        pw = (width - x0 + dx - 1) // dx if width > x0 else 0
        ph = (height - y0 + dy - 1) // dy if height > y0 else 0
        dims.append((pw, ph))
    return dims


def expected_bytes(width, height, bpp, interlace):
    """返回 (期望总字节数, [(趟描述, 行数, 每行字节数)])。"""
    detail = []
    if interlace == 0:
        row = 1 + (width * bpp + 7) // 8
        detail.append(("整图 %dx%d" % (width, height), height, row))
        return height * row, detail
    total = 0
    for i, (pw, ph) in enumerate(pass_dims(width, height), 1):
        if pw == 0 or ph == 0:
            detail.append(("第 %d 趟 (0x0, 空趟)" % i, 0, 0))
            continue
        row = 1 + (pw * bpp + 7) // 8
        total += ph * row
        detail.append(("第 %d 趟 %dx%d" % (i, pw, ph), ph, row))
    return total, detail


def bad_filter_bytes(raw, detail):
    """按每行字节数走查解压数据, 统计行首滤波类型字节取值非法(>4)的行数。"""
    pos = 0
    bad = 0
    for _name, rows, row_bytes in detail:
        if row_bytes == 0:
            continue
        for _r in range(rows):
            if pos >= len(raw):
                break
            if raw[pos] > 4:
                bad += 1
            pos += row_bytes
    return bad


def main(argv=None):
    setup_stdio()
    ap = argparse.ArgumentParser(
        description="按规范公式计算 PNG 扫描线总字节数, 与 IDAT 解压后长度比对验证完整性")
    ap.add_argument("file", help="PNG 文件路径")
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

    if not chunks or chunks[0][1] != b"IHDR" or len(chunks[0][2]) != 13:
        print("错误: 未找到合法的 IHDR 块", file=sys.stderr)
        return 2
    w, h, bd, ct, comp, filt, inter = struct.unpack(">IIBBBBB", chunks[0][2])
    if comp != 0 or filt != 0:
        print("错误: 压缩方法 %d/滤波方法 %d 非 0, 本工具按规范方法 0 计算" % (comp, filt),
              file=sys.stderr)
        return 2
    if inter not in (0, 1):
        print("错误: 隔行方式 %d 非法(只能 0 或 1)" % inter, file=sys.stderr)
        return 2
    if ct not in CHANNELS or bd not in ALLOWED_BD[ct]:
        print("错误: 颜色类型 %d 与位深 %d 组合非法, 无法按公式计算" % (ct, bd), file=sys.stderr)
        return 2
    if not any(c[1] == b"IDAT" for c in chunks):
        print("错误: 文件中没有任何 IDAT 块", file=sys.stderr)
        return 2

    channels = CHANNELS[ct]
    bpp = channels * bd
    expected, detail = expected_bytes(w, h, bpp, inter)
    inter_txt = "Adam7 隔行" if inter else "无隔行"
    print("图像: %dx%d, 颜色类型 %d (%s), 位深 %d, %s" % (w, h, ct, CT_NAMES[ct], bd, inter_txt))
    print("通道数 %d, 每像素 %d 位; 每行 = 1 字节滤波类型 + ceil(行宽 x %d / 8) 字节像素数据"
          % (channels, bpp, bpp))
    for name, rows, row_bytes in detail:
        if rows:
            print("  %s: %d 行 x %d 字节 = %d 字节" % (name, rows, row_bytes, rows * row_bytes))
    print("期望总字节数: %d" % expected)

    idat = b"".join(c[2] for c in chunks if c[1] == b"IDAT")
    try:
        raw = zlib.decompress(idat)
    except zlib.error as exc:
        dobj = zlib.decompressobj()
        partial = b""
        try:
            partial = dobj.decompress(idat)
        except zlib.error:
            pass
        print("IDAT 解压失败: %s" % exc)
        print("部分解压得到 %d 字节(期望 %d 字节)" % (len(partial), expected))
        print("结果: IDAT 数据损坏或截断 (退出码 1)")
        return 1

    actual = len(raw)
    print("实际解压长度: %d" % actual)
    if actual == expected:
        bad = bad_filter_bytes(raw, detail)
        if bad:
            print("警告: %d 个扫描行的滤波类型字节取值非法(应为 0..4)" % bad)
        else:
            print("滤波类型走查: 每行首字节均在 0..4 范围内")
        print("结果: 实际长度与公式一致, 图像数据完整 (退出码 0)")
        return 0

    diff = actual - expected
    print("长度差: %+d" % diff)
    if diff < 0:
        print("提示: 实际数据比期望短, 图像数据可能被截断")
    else:
        print("提示: 实际数据比期望长, 可能混入多余数据或 IHDR 尺寸与数据不符")
    print("结果: 实际长度与公式不一致, 图像数据不完整 (退出码 1)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
