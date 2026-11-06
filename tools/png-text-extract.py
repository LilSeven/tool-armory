#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG 文本提取器：提取 PNG 中 tEXt / zTXt / iTXt 块的关键字-文本对。

块格式（PNG 规范）：
  tEXt: keyword \\0 text                              —— 全 Latin-1
  zTXt: keyword \\0 压缩方法(1 字节, 0=zlib) \\0 压缩文本 —— 关键字 Latin-1，文本 zlib 解压后 Latin-1
  iTXt: keyword \\0 压缩标志 \\0 压缩方法 \\0 语言标签 \\0 翻译关键字 \\0 文本
        —— 文本与翻译关键字为 UTF-8；压缩标志 1 时文本经 zlib 解压

用法：
    python png-text-extract.py <image.png> [--json] [-k KEYWORD]

选项：
    --json          以 JSON 数组输出（ensure_ascii=False）
    -k, --keyword   仅显示关键字精确匹配（不区分大小写）的条目

退出码：
    0 = 正常（没有文本块时输出提示，也返回 0）
    2 = 文件不存在 / 无法读取 / 不是 PNG / PNG 结构损坏

示例：
    python png-text-extract.py photo.png
    python png-text-extract.py photo.png --json
    python png-text-extract.py photo.png -k Comment
"""

import argparse
import json
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


def parse_chunks(data):
    """严格解析 chunk 序列，返回 ([(raw_type, cdata, offset)], warnings)。"""
    if len(data) < 8 or data[:8] != PNG_SIG:
        raise ValueError("不是 PNG 文件（8 字节签名不符）")
    chunks = []
    warnings = []
    pos = 8
    seen_iend = False
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
        chunks.append((raw_type, data[pos + 8:pos + 8 + length], pos))
        pos = end
        if raw_type == b"IEND":
            seen_iend = True
            break
    if not seen_iend:
        warnings.append("未找到 IEND 块")
    elif pos < len(data):
        warnings.append("IEND 之后有 %d 字节多余数据" % (len(data) - pos))
    return chunks, warnings


def decode_text_chunk(raw_type, cdata):
    """把一个文本块解码为 dict；坏数据不抛异常，写入 error 字段。"""
    info = {"type": raw_type.decode("latin-1"), "keyword": None,
            "language": None, "translated_keyword": None,
            "compressed": False, "text": None, "error": None}
    try:
        if raw_type == b"tEXt":
            kw, sep, text = cdata.partition(b"\x00")
            info["keyword"] = kw.decode("latin-1")
            if not sep:
                info["error"] = "缺少关键字后的 NUL 分隔符"
            info["text"] = text.decode("latin-1")
        elif raw_type == b"zTXt":
            kw, sep, rest = cdata.partition(b"\x00")
            info["keyword"] = kw.decode("latin-1")
            if not sep or len(rest) < 1:
                raise ValueError("zTXt 格式不完整（缺少压缩方法字节）")
            if rest[0] != 0:
                raise ValueError("zTXt 压缩方法 %d 不支持（仅支持 0=zlib）" % rest[0])
            info["compressed"] = True
            info["text"] = zlib.decompress(rest[1:]).decode("latin-1")
        elif raw_type == b"iTXt":
            kw, sep, rest = cdata.partition(b"\x00")
            info["keyword"] = kw.decode("latin-1")
            if not sep or len(rest) < 2:
                raise ValueError("iTXt 格式不完整（头部不足 2 字节）")
            comp_flag, comp_method = rest[0], rest[1]
            rest = rest[2:]
            lang, sep2, rest = rest.partition(b"\x00")
            trans, sep3, text = rest.partition(b"\x00")
            info["language"] = lang.decode("latin-1")
            info["translated_keyword"] = trans.decode("utf-8", "replace")
            if comp_flag == 1:
                if comp_method != 0:
                    raise ValueError("iTXt 压缩方法 %d 不支持（仅支持 0=zlib）" % comp_method)
                info["compressed"] = True
                text = zlib.decompress(text)
            elif comp_flag != 0:
                raise ValueError("iTXt 压缩标志 %d 非法（应为 0 或 1）" % comp_flag)
            info["text"] = text.decode("utf-8", "replace")
            if not sep2 or not sep3:
                info["error"] = ((info["error"] + "；") if info["error"] else "")
                + "语言标签/翻译关键字的 NUL 分隔符缺失"
    except (zlib.error, ValueError) as exc:
        info["error"] = str(exc)
        if info["text"] is None:
            info["text"] = ""
    return info


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(description="提取 PNG tEXt/zTXt/iTXt 关键字-文本对")
    ap.add_argument("file", help="PNG 文件路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 数组输出")
    ap.add_argument("-k", "--keyword",
                    help="仅输出关键字精确匹配（不区分大小写）的条目")
    args = ap.parse_args(argv)

    try:
        with open(args.file, "rb") as fh:
            data = fh.read()
        chunks, warnings = parse_chunks(data)
    except (OSError, ValueError) as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 2
    for w in warnings:
        print("警告：%s" % w, file=sys.stderr)

    found = [decode_text_chunk(t, d)
             for t, d, _off in chunks if t in (b"tEXt", b"zTXt", b"iTXt")]
    if args.keyword:
        key = args.keyword.lower()
        found = [f for f in found if (f["keyword"] or "").lower() == key]

    if args.json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
        return 0
    if not found:
        print("未找到 tEXt/zTXt/iTXt 文本块。")
        return 0
    for i, info in enumerate(found, 1):
        head = "[%d] %-4s 关键字: %s" % (i, info["type"], info["keyword"])
        extras = []
        if info["language"]:
            extras.append("语言: %s" % info["language"])
        if info["translated_keyword"]:
            extras.append("翻译: %s" % info["translated_keyword"])
        if info["compressed"]:
            extras.append("zlib 压缩")
        if extras:
            head += "  (" + "，".join(extras) + ")"
        print(head)
        print("    文本: %s" % info["text"])
        if info["error"]:
            print("    警告: %s" % info["error"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
