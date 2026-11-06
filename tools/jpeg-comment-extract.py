#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jpeg-comment-extract —— 提取 JPEG COM 段中的注释文本, 多条逐一列出。

用途:
    扫描 JPEG 文件中的 COM (0xFFFE) 标记段, 把每条注释的偏移、大小与
    文本内容逐一列出 (支持任意条数)。文本按 utf-8 -> gbk -> latin-1
    顺序尝试解码并标注所用字符集; 控制字符以 \\xNN 转义显示, 避免破坏
    终端。--hex 可额外输出每条注释的原始字节十六进制。

用法:
    python -I jpeg-comment-extract.py <file.jpg> [--hex] [--json]

示例:
    python -I jpeg-comment-extract.py photo.jpg
    python -I jpeg-comment-extract.py photo.jpg --hex
    python -I jpeg-comment-extract.py photo.jpg --json

退出码: 0=成功 (没有 COM 段也返回 0, 输出 comments: 0); 1=不是 JPEG 或
结构损坏/截断; 2=命令行参数错误。
仅使用 Python 标准库。
"""

import argparse
import json
import sys

CHARSETS = ("utf-8", "gbk", "latin-1")


class JpegError(Exception):
    """JPEG 结构错误。"""


def scan(data):
    """扫描到 SOS/EOI 为止, 返回 (comments, stop_note)。

    comment 为 dict: index/offset/size/raw。
    offset 指向 COM 标记码前的 0xFF; size 为整个 COM 段字节数。
    """
    n = len(data)
    if n < 2 or data[0] != 0xFF or data[1] != 0xD8:
        raise JpegError("not a JPEG file (missing SOI FF D8)")
    comments = []
    pos = 2
    stop_note = None
    while pos < n:
        start = pos
        while pos < n and data[pos] == 0xFF:      # 跳过填充字节
            pos += 1
        if pos >= n:
            stop_note = "truncated after offset %d (no terminating marker)" % start
            break
        if data[pos] == 0x00:
            raise JpegError("stray 0x00 after fill bytes at offset %d" % start)
        m = data[pos]
        moff = pos - 1                             # 标记码前最近的 0xFF
        if data[moff] != 0xFF:
            raise JpegError("desync: expected 0xFF at offset %d before marker "
                            "0x%02X" % (moff, m))
        pos += 1
        if m == 0xD9:
            stop_note = "EOI at offset %d" % moff
            break
        if m == 0xDA:
            stop_note = "SOS at offset %d (compressed image data starts)" % moff
            break
        if m == 0x01 or 0xD0 <= m <= 0xD7:         # TEM / RSTn, 无长度字段
            continue
        if pos + 2 > n:
            raise JpegError("file truncated before length field of marker "
                            "0x%02X at offset %d" % (m, moff))
        seglen = (data[pos] << 8) | data[pos + 1]
        if seglen < 2:
            raise JpegError("invalid segment length %d for marker 0x%02X at "
                            "offset %d" % (seglen, m, moff))
        total = 2 + seglen
        if moff + total > n:
            raise JpegError("segment 0x%02X at offset %d exceeds file size "
                            "(truncated)" % (m, moff))
        if m == 0xFE:                              # COM
            raw = data[moff + 4:moff + 2 + seglen]
            comments.append({"index": len(comments), "offset": moff,
                             "size": total, "raw": raw})
        pos = moff + total
    return comments, stop_note


def decode(raw):
    """按 utf-8 -> gbk -> latin-1 顺序解码, 返回 (文本, 字符集名)。"""
    for enc in CHARSETS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1"), "latin-1"        # latin-1 不会失败, 兜底


def display(text):
    """把控制字符转义为 \\xNN, 保留可打印字符 (含中文)。"""
    out = []
    for ch in text:
        if ch.isprintable() or ch in "\t\n\r":
            out.append(ch)
        else:
            out.append("\\x%02X" % (ord(ch) & 0xFF))
    return "".join(out)


def human_report(path, size, comments, stop_note, show_hex):
    lines = [
        "file: %s" % path,
        "size: %d bytes" % size,
        "comments: %d" % len(comments),
    ]
    if not comments:
        lines.append("no COM segment found")
    for c in comments:
        text, enc = decode(c["raw"])
        lines.append("")
        lines.append("[%d] offset=%d (0x%X) size=%d bytes charset=%s"
                     % (c["index"], c["offset"], c["offset"], c["size"], enc))
        lines.append("    %s" % display(text))
        if show_hex:
            hexs = " ".join("%02X" % b for b in c["raw"])
            lines.append("    hex: %s" % hexs)
    if stop_note:
        lines.append("")
        lines.append("(scan stopped: %s)" % stop_note)
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="jpeg-comment-extract",
        description="提取 JPEG COM 段中的注释文本, 多条注释逐一列出。")
    ap.add_argument("file", help="JPEG 文件路径")
    ap.add_argument("--hex", action="store_true", help="同时输出每条注释的原始字节十六进制")
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
        comments, stop_note = scan(data)
    except JpegError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1

    if args.json:
        out_comments = []
        for c in comments:
            text, enc = decode(c["raw"])
            out_comments.append({"index": c["index"], "offset": c["offset"],
                                 "size": c["size"], "charset": enc,
                                 "text": text,
                                 "hex": c["raw"].hex()})
        out = {"file": args.file, "size": len(data), "comments": out_comments,
               "stop": stop_note}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(human_report(args.file, len(data), comments, stop_note, args.hex))
    return 0


if __name__ == "__main__":
    sys.exit(main())
