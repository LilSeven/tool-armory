#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG 文本写入器：向 PNG 追加或替换指定关键字的 tEXt 块，重排 IEND 后输出新文件。

行为：
  * 新 tEXt 块总是插在 IEND 之前（即“重排 IEND”——IEND 仍是最后一个块）；
  * --mode replace（默认）：先删除所有同关键字的旧 tEXt 块，再插入新块；
  * --mode append：保留旧块，直接插入新块（允许同关键字多块并存）；
  * 重建文件时按新数据重算所有块的 CRC（zlib.crc32）。

说明：
  * tEXt 的关键字（1-79 字节）与文本均为 Latin-1；含非 Latin-1 字符时报错退出
    （如需 UTF-8/多语言文本请改用 iTXt，本工具不涉及）。
  * 未指定 -o 时，输出文件为 <输入名去扩展名>.text.png。

用法：
    python png-text-set.py <in.png> -k 关键字 -t 文本 [-o out.png] [--mode replace|append]

退出码：
    0 = 成功写出新文件（已自检：新块存在且 IEND 仍为最后一块）
    1 = 输入不是合法 PNG 或结构不满足写入条件（缺 IEND / 块截断 / IEND 后有数据）
    2 = 文件无法读取 / 无法写出 / 参数或编码错误

示例：
    python png-text-set.py photo.png -k Software -t "tool-armory 1.0" -o photo-tagged.png
    python png-text-set.py photo.png -k Comment -t "hello" --mode append -o photo2.png
"""

import argparse
import os
import struct
import sys
import zlib

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def is_valid_type(raw):
    return len(raw) == 4 and all(65 <= c <= 90 or 97 <= c <= 122 for c in raw)


def load_chunks(data):
    """严格解析为 [(raw_type, cdata)]；要求 IEND 存在且其后无数据。"""
    if len(data) < 8 or data[:8] != PNG_SIG:
        raise ValueError("不是 PNG 文件（8 字节签名不符）")
    chunks = []
    pos = 8
    while pos < len(data):
        if len(data) - pos < 8:
            raise ValueError("offset %d：剩余数据不足一个块头（文件截断）" % pos)
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        raw_type = data[pos + 4:pos + 8]
        if not is_valid_type(raw_type):
            raise ValueError("offset %d：块类型字节非法" % pos)
        end = pos + 8 + length + 4
        if end > len(data):
            raise ValueError("块 %s 被截断（声明 %d 字节，仅剩 %d）"
                             % (raw_type.decode("latin-1"), length,
                                len(data) - pos - 8))
        chunks.append((raw_type, data[pos + 8:pos + 8 + length]))
        pos = end
        if raw_type == b"IEND":
            break
    if not chunks or chunks[-1][0] != b"IEND":
        raise ValueError("未找到 IEND 块，PNG 数据流不完整")
    if pos < len(data):
        raise ValueError("IEND 之后有 %d 字节多余数据" % (len(data) - pos))
    return chunks


def build_png(chunks):
    out = [PNG_SIG]
    for raw_type, cdata in chunks:
        out.append(struct.pack(">I", len(cdata)))
        out.append(raw_type)
        out.append(cdata)
        out.append(struct.pack(">I", zlib.crc32(raw_type + cdata) & 0xFFFFFFFF))
    return b"".join(out)


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(description="向 PNG 追加/替换指定关键字的 tEXt 块")
    ap.add_argument("file", help="输入 PNG 文件")
    ap.add_argument("-k", "--keyword", required=True,
                    help="tEXt 关键字（1-79 字节 Latin-1）")
    ap.add_argument("-t", "--text", required=True, help="tEXt 文本（Latin-1）")
    ap.add_argument("-o", "--output",
                    help="输出文件路径（默认 <输入名去扩展名>.text.png）")
    ap.add_argument("--mode", choices=("replace", "append"), default="replace",
                    help="replace=替换同关键字旧 tEXt（默认）；append=保留旧块追加")
    args = ap.parse_args(argv)

    try:
        kw_b = args.keyword.encode("latin-1")
    except UnicodeEncodeError:
        print("错误：关键字含非 Latin-1 字符，tEXt 不支持", file=sys.stderr)
        return 2
    if not (1 <= len(kw_b) <= 79) or args.keyword != args.keyword.strip() \
            or "\x00" in args.keyword:
        print("错误：关键字须为 1-79 字节、无前后空白、不含 NUL", file=sys.stderr)
        return 2
    try:
        text_b = args.text.encode("latin-1")
    except UnicodeEncodeError:
        print("错误：文本含非 Latin-1 字符，tEXt 不支持"
              "（如需 UTF-8 多语言文本请改用 iTXt 工具）", file=sys.stderr)
        return 2
    if b"\x00" in text_b:
        print("错误：文本不能包含 NUL 字节", file=sys.stderr)
        return 2

    try:
        with open(args.file, "rb") as fh:
            data = fh.read()
        chunks = load_chunks(data)
    except OSError as exc:
        print("错误：无法读取文件：%s" % exc, file=sys.stderr)
        return 2
    except ValueError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 1

    new_data = kw_b + b"\x00" + text_b
    kept = []
    removed = 0
    for raw_type, cdata in chunks:
        if (args.mode == "replace" and raw_type == b"tEXt"
                and cdata.partition(b"\x00")[0] == kw_b):
            removed += 1
            continue
        kept.append((raw_type, cdata))

    rebuilt = []
    inserted_at = None
    for raw_type, cdata in kept:
        if raw_type == b"IEND" and inserted_at is None:
            inserted_at = len(rebuilt)
            rebuilt.append((b"tEXt", new_data))
        rebuilt.append((raw_type, cdata))
    if inserted_at is None:  # load_chunks 已保证 IEND 存在，此处仅为兜底
        inserted_at = len(rebuilt)
        rebuilt.append((b"tEXt", new_data))

    out_path = args.output
    if not out_path:
        root, ext = os.path.splitext(args.file)
        out_path = root + ".text" + (ext or ".png")
    try:
        with open(out_path, "wb") as fh:
            fh.write(build_png(rebuilt))
    except OSError as exc:
        print("错误：无法写出文件：%s" % exc, file=sys.stderr)
        return 2

    # 写后自检：重新解析输出，确认新块存在且 IEND 仍是最后一块
    try:
        with open(out_path, "rb") as fh:
            check = load_chunks(fh.read())
    except (OSError, ValueError) as exc:
        print("错误：输出文件自检失败：%s" % exc, file=sys.stderr)
        return 1
    present = any(t == b"tEXt" and d.partition(b"\x00")[0] == kw_b
                  for t, d in check)
    if not present or check[-1][0] != b"IEND":
        print("错误：输出自检未通过", file=sys.stderr)
        return 1
    print("完成：%s（%d 个 chunk，自检通过）" % (out_path, len(rebuilt)))
    print("  模式=%s，删除旧块 %d 个，新 tEXt '%s' 位于索引 %d（IEND 之前），"
          "IEND 仍为最后一块" % (args.mode, removed, args.keyword, inserted_at))
    return 0


if __name__ == "__main__":
    sys.exit(main())
