#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""终端字符接触表（contact-sheet-text）。

用途：
    读取一批图片的文件头尺寸，用字符方块在终端按真实宽高比画出每张图的
    相对大小示意：大图占的方块多、小图占的少，且形状比例与像素比例一致。
    终端字符"高约等于宽的 2 倍"，因此纵向行数按 --char-aspect（默认 2.0）
    折算，画出的形状肉眼接近真实比例。只读文件头，不修改任何文件。

用法：
    python contact-sheet-text.py D:/pics
    python contact-sheet-text.py a.png b.png c.png
    python contact-sheet-text.py D:/pics --cols 60 --fill '#' --max-rows 30

选项：
    --cols         最宽的图占多少字符列（默认 48），其余按比例缩放
    --fill         方块字符（默认 '█'；终端不支持时可改 '#'）
    --max-rows     单图最大行数，超过则所有图整体等比压缩（默认 60）
    --char-aspect  终端字符高/宽比（默认 2.0）

支持格式：PNG / JPEG / GIF / BMP / WebP。

退出码：0 成功；1 没有任何可读取的图片；2 参数错误。
"""
import argparse
import os
import struct
import sys

EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


def probe_size(path):
    """解析文件头，返回 (宽, 高)；无法识别时抛 ValueError。"""
    with open(path, "rb") as fp:
        head = fp.read(32)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            fp.seek(16)
            buf = fp.read(8)
            if len(buf) < 8:
                raise ValueError("PNG IHDR 不完整")
            w, h = struct.unpack(">II", buf)
            return w, h
        if head[:6] in (b"GIF87a", b"GIF89a"):
            if len(head) < 10:
                raise ValueError("GIF 头不完整")
            w, h = struct.unpack("<HH", head[6:10])
            return w, h
        if head[:2] == b"BM":
            if len(head) < 26:
                raise ValueError("BMP 头不完整")
            dib = struct.unpack("<I", head[14:18])[0]
            if dib == 12:  # BITMAPCOREHEADER：字段为 16 位
                w, h = struct.unpack("<HH", head[18:22])
            else:
                w, h = struct.unpack("<ii", head[18:26])
            return abs(w), abs(h)
        if head[:2] == b"\xff\xd8":
            return _probe_jpeg(fp)
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            fp.seek(12)
            fourcc = fp.read(4)
            payload = fp.read(10)
            if fourcc == b"VP8 ":
                if len(payload) < 10 or payload[3:6] != b"\x9d\x01\x2a":
                    raise ValueError("VP8 帧头异常")
                w, h = struct.unpack("<HH", payload[6:10])
                return w & 0x3FFF, h & 0x3FFF
            if fourcc == b"VP8L":
                if len(payload) < 4 or payload[0] != 0x2F:
                    raise ValueError("VP8L 帧头异常")
                bits = struct.unpack("<I", payload[:4])[0]
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            if fourcc == b"VP8X":
                if len(payload) < 10:
                    raise ValueError("VP8X 帧头异常")
                w = int.from_bytes(payload[4:7], "little") + 1
                h = int.from_bytes(payload[7:10], "little") + 1
                return w, h
            raise ValueError("不支持的 WebP 子块：%r" % fourcc)
    raise ValueError("不是可识别的图片格式")


def _probe_jpeg(fp):
    """沿 JPEG 标记链寻找 SOFn 段读取尺寸。"""
    fp.seek(2)
    while True:
        b = fp.read(1)
        if not b:
            raise ValueError("未找到 SOF 段")
        if b != b"\xff":
            continue
        m = fp.read(1)
        if not m:
            raise ValueError("文件在标记处截断")
        while m == b"\xff":
            m = fp.read(1)
        if not m:
            raise ValueError("文件在标记处截断")
        code = m[0]
        if code == 0x00 or code in (0x01, 0xD8) or 0xD0 <= code <= 0xD7:
            continue  # 填充字节或无长度字段的独立标记
        buf = fp.read(2)
        if len(buf) < 2:
            raise ValueError("段长度不完整")
        seglen = struct.unpack(">H", buf)[0]
        if seglen < 2:
            raise ValueError("段长度非法")
        if 0xC0 <= code <= 0xCF and code not in (0xC4, 0xC8, 0xCC):
            buf = fp.read(5)
            if len(buf) < 5:
                raise ValueError("SOF 段不完整")
            h, w = struct.unpack(">HH", buf[1:5])
            return w, h
        fp.seek(seglen - 2, 1)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="用字符方块在终端按真实宽高比预览图片相对大小")
    ap.add_argument("inputs", nargs="+", help="图片文件或目录（目录递归收集）")
    ap.add_argument("--cols", type=int, default=48, metavar="N",
                    help="最宽的图占的字符列数（默认 48）")
    ap.add_argument("--fill", default="█", metavar="C",
                    help="方块字符（默认 '█'）")
    ap.add_argument("--max-rows", type=int, default=60, metavar="N",
                    help="单图最大行数，超出则整体等比压缩（默认 60）")
    ap.add_argument("--char-aspect", type=float, default=2.0, metavar="R",
                    help="终端字符高/宽比（默认 2.0）")
    args = ap.parse_args(argv)

    if len(args.fill) != 1:
        ap.error("--fill 必须是单个字符")
    if args.cols < 4 or args.max_rows < 2 or args.char_aspect <= 0:
        ap.error("--cols/--max-rows/--char-aspect 取值不合理")

    items, bad = [], []
    seen = set()

    def add_file(p):
        key = os.path.abspath(p)
        if key in seen:
            return
        seen.add(key)
        try:
            w, h = probe_size(p)
            items.append({"file": p, "width": w, "height": h})
        except Exception as exc:
            bad.append((p, str(exc)))

    for p in args.inputs:
        if os.path.isdir(p):
            for dirpath, dirnames, filenames in os.walk(p):
                dirnames.sort()
                for name in sorted(filenames):
                    if os.path.splitext(name)[1].lower() in EXTS:
                        add_file(os.path.join(dirpath, name))
        else:
            add_file(p)

    for p, err in bad:
        print("!! 跳过 %s：%s" % (p, err), file=sys.stderr)
    if not items:
        print("没有可读取的图片。", file=sys.stderr)
        return 1

    max_w = max(it["width"] for it in items)
    k = args.cols / max_w

    def layout(k):
        for it in items:
            it["cols"] = max(1, round(it["width"] * k))
            it["rows"] = max(1, round(it["height"] * k / args.char_aspect))

    layout(k)
    tallest = max(it["rows"] for it in items)
    note = ""
    if tallest > args.max_rows:
        k *= args.max_rows / tallest
        layout(k)
        note = "（已按 --max-rows=%d 整体等比压缩）" % args.max_rows

    for it in items:
        print("%s  %dx%d" % (it["file"], it["width"], it["height"]))
        for _ in range(it["rows"]):
            print(args.fill * it["cols"])
        print()
    print("# 比例：1 字符 ≈ %.1f px 宽，1 行 ≈ %.1f px 高%s"
          % (1 / k, args.char_aspect / k, note))
    return 0


if __name__ == "__main__":
    sys.exit(main())
