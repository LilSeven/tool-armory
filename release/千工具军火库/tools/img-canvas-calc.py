#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拼贴画布计算 — 给定一批图片与列数，计算紧凑网格拼贴所需的总画布尺寸与每张摆放坐标。

排布规则（行优先、不缩放、保持原始像素尺寸）:
  * 按 --cols 张一行切分行; 行高 = 行内最高图片的高度;
  * 行内图片从左到右依次摆放, 列间距 = gap, 行间距 = gap, 画布四周留 margin;
  * 画布宽 = 最宽一行(含 margin), 画布高 = 各行高之和(含行间 gap 与 margin);
  * --sort h 按高度降序分组, 行内高度接近时空间利用率更高。
GIF 取逻辑屏幕尺寸。输出画布总尺寸、每张的左上角 (x, y) 坐标与空间利用率。

用法:
    python img-canvas-calc.py a.png b.jpg c.gif --cols 3
    python img-canvas-calc.py ./tiles --cols 4 --gap 4 --margin 2 --sort h
    python img-canvas-calc.py ./tiles --cols 2 --json
    # 中文乱码时: python -X utf8 img-canvas-calc.py ./tiles --cols 3

无可用图片时退出码 1; 参数错误走 argparse（退出码 2）。只读，不修改任何文件。仅用标准库。
"""

import argparse
import json
import os
import struct
import sys

IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}
SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
               0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _setup_stdio():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def collect_paths(paths, exts=IMG_EXTS):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                if os.path.splitext(name)[1].lower() in exts:
                    out.append(os.path.join(p, name))
        else:
            out.append(p)
    return out


# ---------------- 尺寸读取 ----------------
def jpeg_dims(data):
    if data[:2] != b"\xff\xd8":
        return None
    i, n = 2, len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            break
        m = data[i + 1]
        if m == 0xFF:
            i += 1
            continue
        if m == 0x01 or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        if m in (0xD8, 0xD9):
            break
        (ln,) = struct.unpack_from(">H", data, i + 2)
        if ln < 2:
            break
        if m in SOF_MARKERS:
            if i + 9 > n:
                return "JPEG", None, None
            h, w = struct.unpack_from(">HH", data, i + 5)
            return "JPEG", w, h
        i += 2 + ln
    return "JPEG", None, None


def png_dims(data):
    if data[:8] != PNG_SIG:
        return None
    i, n = 8, len(data)
    while i + 8 <= n:
        (ln,) = struct.unpack_from(">I", data, i)
        typ = data[i + 4:i + 8]
        if typ == b"IHDR" and ln >= 8:
            w, h = struct.unpack_from(">II", data, i + 8)
            return "PNG", w, h
        i += 12 + ln
        if typ == b"IEND":
            break
    return "PNG", None, None


def image_dims(data):
    """返回 (fmt, w, h); 无法识别返回 None。GIF 取逻辑屏幕, BMP 取位图头。"""
    got = jpeg_dims(data)
    if got:
        return got
    got = png_dims(data)
    if got:
        return got
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        w, h = struct.unpack_from("<HH", data, 6)
        return "GIF", w, h
    if data[:2] == b"BM" and len(data) >= 26:
        w, h = struct.unpack_from("<ii", data, 18)
        return "BMP", w, abs(h)
    return None


def dims_of(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    got = image_dims(data)
    if got is None or not got[1]:
        return None
    return got


# ---------------- 画布计算 ----------------
def compute(items, cols, gap, margin):
    """items: [(file, w, h)]; 返回 (canvas_w, canvas_h, placements)。"""
    rows = [items[i:i + cols] for i in range(0, len(items), cols)]
    placements = []
    y = margin
    canvas_w = 0
    for ri, row in enumerate(rows, 1):
        row_h = max(h for _, _, h in row)
        x = margin
        for p, w, h in row:
            placements.append({"file": p, "row": ri, "x": x, "y": y, "w": w, "h": h})
            x += w + gap
        inner = x - gap - margin
        canvas_w = max(canvas_w, inner + 2 * margin)
        y += row_h + gap
    canvas_h = y - gap + margin
    return canvas_w, canvas_h, placements


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="拼贴画布计算: 紧凑网格的总画布尺寸与每张摆放坐标")
    ap.add_argument("paths", nargs="+",
                    help="图片文件或目录（目录仅查 jpg/jpeg/png/gif/bmp）")
    ap.add_argument("--cols", type=int, default=3, help="每行列数 (默认 3)")
    ap.add_argument("--gap", type=int, default=0, help="图片间距, 像素 (默认 0)")
    ap.add_argument("--margin", type=int, default=0, help="画布四周留白, 像素 (默认 0)")
    ap.add_argument("--sort", choices=("none", "h", "w"), default="none",
                    help="排序: none=给定顺序, h=按高降序, w=按宽降序")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args(argv)
    _setup_stdio()
    if args.cols < 1:
        ap.error("--cols 必须 >= 1")
    if args.gap < 0 or args.margin < 0:
        ap.error("--gap/--margin 必须 >= 0")

    items, skipped = [], []
    for p in collect_paths(args.paths):
        got = dims_of(p)
        if got:
            items.append((p, got[1], got[2]))
        else:
            skipped.append(p)
    if args.sort == "h":
        items.sort(key=lambda t: (-t[2], -t[1], t[0]))
    elif args.sort == "w":
        items.sort(key=lambda t: (-t[1], -t[2], t[0]))
    if not items:
        print("没有可解析尺寸的图片，无法计算画布。", file=sys.stderr)
        return 1

    cw, ch, placements = compute(items, args.cols, args.gap, args.margin)
    used = sum(w * h for _, w, h in items)
    total = cw * ch
    util = used / total * 100 if total else 0.0

    if args.json:
        print(json.dumps({
            "canvas": {"width": cw, "height": ch},
            "cols": args.cols, "gap": args.gap, "margin": args.margin,
            "sort": args.sort, "count": len(items),
            "utilization_pct": round(util, 1),
            "skipped": skipped, "placements": placements,
        }, ensure_ascii=False, indent=2))
        return 0

    print("输入 %d 张图 | %d 列 | gap=%d | margin=%d | 排序=%s"
          % (len(items), args.cols, args.gap, args.margin, args.sort))
    if skipped:
        print("警告: 跳过 %d 个无法解析尺寸的文件: %s" % (len(skipped), ", ".join(skipped)))
    print("画布总尺寸: %d x %d (像素)" % (cw, ch))
    print("空间利用率: %.1f%% (图片面积合计 %d px² / 画布 %d px²)"
          % (util, used, total))
    print("摆放坐标 (左上角原点, 按原始尺寸不缩放):")
    print("  行  %-34s %-12s %s" % ("文件", "尺寸", "x,y"))
    for pl in placements:
        print("  %2d  %-34s %-12s %d,%d" % (
            pl["row"], pl["file"], "%dx%d" % (pl["w"], pl["h"]),
            pl["x"], pl["y"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
