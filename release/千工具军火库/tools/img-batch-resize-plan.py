#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量缩放方案生成器（img-batch-resize-plan）。

用途：
    给定目标最长边，解析每张图片的文件头得到真实尺寸，计算各自应缩放到的
    精确像素尺寸（长边对齐目标，短边按比例取整，最小 1px）。
    只输出方案，绝不修改任何文件。

规则：
    新尺寸 = 原尺寸 * (目标最长边 / 当前最长边)，按比例取整（round）且不小于 1。
    当前最长边已 <= 目标时默认"保持原尺寸"；加 --upscale 才会放大。

支持格式：PNG / JPEG / GIF / BMP / WebP。

示例命令：
    python img-batch-resize-plan.py --target 1024 a.png b.png
    python img-batch-resize-plan.py --target 1024 --dir D:/pics
    python img-batch-resize-plan.py --target 1024 --dir D:/pics --json
    python img-batch-resize-plan.py --target 2048 --upscale small.png

退出码：0 成功（个别文件解析失败会列入 skipped 并写到 stderr，不影响退出码）；
        2 参数错误或目录不存在。
"""
import argparse
import json
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


def plan_for(w, h, target, upscale):
    long_side = max(w, h)
    if long_side <= target and not upscale:
        return {"action": "keep", "new_width": w, "new_height": h, "scale": 1.0}
    scale = target / long_side
    return {"action": "resize",
            "new_width": max(1, round(w * scale)),
            "new_height": max(1, round(h * scale)),
            "scale": round(scale, 4)}


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="按目标最长边生成批量缩放方案（只出方案，不改文件）")
    ap.add_argument("files", nargs="*", help="图片文件（可与 --dir 同用）")
    ap.add_argument("--dir", help="目录：递归收集其中的图片")
    ap.add_argument("--target", type=int, required=True,
                    help="目标最长边（像素，正整数）")
    ap.add_argument("--upscale", action="store_true",
                    help="最长边已小于目标的图也放大到目标边")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出方案")
    args = ap.parse_args(argv)

    if args.target <= 0:
        ap.error("--target 必须是正整数")

    paths = list(args.files)
    if args.dir:
        if not os.path.isdir(args.dir):
            print("错误：目录不存在：%s" % args.dir, file=sys.stderr)
            return 2
        for dirpath, dirnames, filenames in os.walk(args.dir):
            dirnames.sort()
            for name in sorted(filenames):
                if os.path.splitext(name)[1].lower() in EXTS:
                    paths.append(os.path.join(dirpath, name))
    if not paths:
        ap.error("未指定任何图片文件或目录")

    items, skipped = [], []
    seen = set()
    for p in paths:
        key = os.path.abspath(p)
        if key in seen:
            continue
        seen.add(key)
        if not os.path.isfile(p):
            skipped.append({"file": p, "error": "文件不存在"})
            continue
        try:
            w, h = probe_size(p)
        except Exception as exc:
            skipped.append({"file": p, "error": str(exc)})
            continue
        pl = plan_for(w, h, args.target, args.upscale)
        items.append({"file": p, "width": w, "height": h,
                      "action": pl["action"], "new_width": pl["new_width"],
                      "new_height": pl["new_height"], "scale": pl["scale"]})

    if args.json:
        print(json.dumps({"target": args.target, "upscale": args.upscale,
                          "items": items, "skipped": skipped},
                         ensure_ascii=False, indent=2))
        return 0

    for it in items:
        if it["action"] == "keep":
            print("%s  %dx%d  ->  保持原尺寸（最长边已 <= %d）"
                  % (it["file"], it["width"], it["height"], args.target))
        else:
            print("%s  %dx%d  ->  %dx%d  (x%.4f)"
                  % (it["file"], it["width"], it["height"],
                     it["new_width"], it["new_height"], it["scale"]))
    for s in skipped:
        print("!! 跳过 %s：%s" % (s["file"], s["error"]), file=sys.stderr)
    print("共 %d 项方案，跳过 %d 项（目标最长边 %d）"
          % (len(items), len(skipped), args.target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
