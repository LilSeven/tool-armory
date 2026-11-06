#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG IDAT 统计 —— 统计 IDAT 块个数、压缩总量、占文件比例与大小分布。

统计 PNG 文件中 IDAT 块的个数、压缩数据总字节数及其占文件大小的比例;
给出每块大小分布(最小/最大/平均/中位数)与逐块明细(序号/偏移/大小/占比)。
多个 IDAT 按规范必须连续排列, 若其间夹杂其他块会给出警告; 若 IEND 之后
存在残留数据也会提示(可用 png-trailer-check 深查)。

用法:
    python png-idat-stats.py <文件.png> [--list N]

参数:
    --list N   逐块明细最多列 N 块(默认 32, 0 表示不列明细)

退出码:
    0 = 统计完成
    1 = 文件中没有任何 IDAT 块
    2 = 文件不存在、无法读取, 或 PNG 签名不符

示例:
    python png-idat-stats.py photo.png
    python png-idat-stats.py photo.png --list 5

仅使用 Python 标准库, 需 Python 3.7+。
"""

import argparse
import statistics
import struct
import sys
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"


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


def main(argv=None):
    setup_stdio()
    ap = argparse.ArgumentParser(
        description="统计 PNG IDAT 块个数、压缩数据总量、占文件比例与每块大小分布")
    ap.add_argument("file", help="PNG 文件路径")
    ap.add_argument("--list", type=int, default=32,
                    help="逐块明细最多列 N 块(默认 32, 0 不列)")
    args = ap.parse_args(argv)

    try:
        with open(args.file, "rb") as fh:
            blob = fh.read()
    except OSError as exc:
        print("错误: 无法读取文件: %s" % exc, file=sys.stderr)
        return 2

    size = len(blob)
    print("文件: %s (%d 字节)" % (args.file, size))
    if not blob.startswith(SIGNATURE):
        print("错误: PNG 签名不符, 不是有效的 PNG 文件", file=sys.stderr)
        return 2

    chunks, stop, problem = parse_chunks(blob)
    if problem:
        print("警告: %s" % problem)
    elif stop < size:
        print("提示: IEND 之后还有 %d 字节残留数据(占比按整个文件计算; 可用 png-trailer-check 深查)"
              % (size - stop))

    idat_idx = [i for i, c in enumerate(chunks) if c[1] == b"IDAT"]
    if not idat_idx:
        print("未找到任何 IDAT 块 (退出码 1)")
        return 1

    idats = [chunks[i] for i in idat_idx]
    sizes = [len(c[2]) for c in idats]
    total = sum(sizes)
    print("IDAT 块数: %d" % len(idats))
    print("压缩数据总计: %d 字节, 占文件 %.1f%%" % (total, total / size * 100 if size else 0.0))
    print("大小分布: 最小 %d, 最大 %d, 平均 %.1f, 中位数 %.1f"
          % (min(sizes), max(sizes), statistics.mean(sizes), statistics.median(sizes)))

    if len(idat_idx) > 1:
        if idat_idx[-1] - idat_idx[0] + 1 != len(idat_idx):
            inter = [chunks[i][1].decode("latin-1")
                     for i in range(idat_idx[0] + 1, idat_idx[-1])
                     if chunks[i][1] != b"IDAT"]
            print("警告: IDAT 之间夹杂其他块(规范要求连续): %s" % ", ".join(inter))
        else:
            print("连续性: 多个 IDAT 连续排列, 符合规范")

    bad_crc = ["偏移 %d" % c[0] for c in idats if not c[3]]
    if bad_crc:
        print("警告: IDAT CRC 校验失败: %s" % ", ".join(bad_crc))

    if args.list:
        shown = idats[:max(0, args.list)]
        print("每块明细 (列出 %d/%d 块):" % (len(shown), len(idats)))
        for k, (off, _ctype, payload, _crc) in enumerate(shown, 1):
            pct = len(payload) / total * 100 if total else 0.0
            print("  #%-3d 偏移 %-8d 大小 %d 字节 (%5.1f%%)"
                  % (k, off, len(payload), pct))
        if len(shown) < len(idats):
            print("  ... 其余 %d 块未列出(可用 --list 调整)" % (len(idats) - len(shown)))
    print("结果: 统计完成 (退出码 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
