#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件名尺寸核对 — 从文件名解析 WxH 标注并与真实头部尺寸比对，找出标注不符的下载图片。

文件名形如 download_800x600.png / photo-1920X1080.jpg / pic 64x64.jpg 时，
自动取文件名里最后一个 "宽x高" 数字对（支持 x / X / ×，允许两侧空格），
与文件头真实尺寸比对（JPEG SOF / PNG IHDR / GIF 逻辑屏幕 / BMP 位图头）：
  标注相符 | 标注不符 | 方向互换(宽高颠倒, 常见于旋转图) | 未标注
结尾单独汇总"标注不符/方向互换"清单，便于批量重命名或退回重下。

用法:
    python img-name-parse.py download_800x600.png wallpaper_3840x2160.jpg
    python img-name-parse.py ./downloads
    python img-name-parse.py ./downloads --json
    # 中文乱码时: python -X utf8 img-name-parse.py ./downloads

退出码恒为 0（标注不符是"发现"不是错误）。只读，不修改任何文件。仅用标准库。
"""

import argparse
import json
import os
import re
import struct
import sys

IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}
DIM_RE = re.compile(r"(\d{2,5})\s*[xX×]\s*(\d{2,5})")
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


def parse_name_wxh(path):
    """从文件名主干取最后一个 WxH 数字对; 无则 None。"""
    stem = os.path.splitext(os.path.basename(path))[0]
    matches = DIM_RE.findall(stem)
    if not matches:
        return None
    w, h = matches[-1]
    return int(w), int(h)


def jpeg_dims(data):
    """返回 ("JPEG", w, h) / ("JPEG", None, None) / None(非JPEG)。"""
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
    """返回 (fmt, w, h); 无法识别返回 None。GIF 取逻辑屏幕尺寸。"""
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


TAG_CN = {"OK": "标注相符", "MISMATCH": "标注不符", "SWAPPED": "方向互换",
          "NO-DIM": "未标注  ", "UNSUPPORTED": "无法识别", "ERROR": "读取失败"}


def analyze(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        return {"file": path, "status": "ERROR", "error": str(e)}
    got = image_dims(data)
    if got is None:
        return {"file": path, "status": "UNSUPPORTED", "error": "不是可识别的图片格式"}
    fmt, w, h = got
    if not w:
        return {"file": path, "status": "ERROR", "error": "%s 文件头不完整" % fmt}
    named = parse_name_wxh(path)
    item = {"file": path, "fmt": fmt, "real_w": w, "real_h": h,
            "named": list(named) if named else None}
    if named is None:
        item["status"] = "NO-DIM"
    elif named == (w, h):
        item["status"] = "OK"
    elif named == (h, w):
        item["status"] = "SWAPPED"
    else:
        item["status"] = "MISMATCH"
    return item


def print_report(rows):
    bad = []
    for r in rows:
        st = r["status"]
        if st in ("OK", "MISMATCH", "SWAPPED", "NO-DIM"):
            named = ("%dx%d" % tuple(r["named"])) if r["named"] else "-"
            print("%s  %s  标注=%-11s 实际=%dx%d (%s)" % (
                TAG_CN[st], r["file"], named, r["real_w"], r["real_h"], r["fmt"]))
        else:
            print("%s  %s  %s" % (TAG_CN[st], r["file"], r.get("error", "")))
        if st in ("MISMATCH", "SWAPPED"):
            bad.append(r)
    cnt = {}
    for r in rows:
        cnt[r["status"]] = cnt.get(r["status"], 0) + 1
    print("-" * 72)
    print("共 %d 个文件: 相符 %d, 不符 %d, 方向互换 %d, 未标注 %d, 跳过 %d" % (
        len(rows), cnt.get("OK", 0), cnt.get("MISMATCH", 0), cnt.get("SWAPPED", 0),
        cnt.get("NO-DIM", 0), cnt.get("UNSUPPORTED", 0) + cnt.get("ERROR", 0)))
    if bad:
        print("标注不符清单 (需重点核对 %d 张):" % len(bad))
        for r in bad:
            note = "（方向互换，疑似旋转图）" if r["status"] == "SWAPPED" else ""
            print("  - %s  标注 %dx%d, 实际 %dx%d%s" % (
                r["file"], r["named"][0], r["named"][1],
                r["real_w"], r["real_h"], note))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="文件名尺寸核对: 文件名 WxH 标注 vs 真实头部尺寸")
    ap.add_argument("paths", nargs="+",
                    help="图片文件或目录（目录仅查 jpg/jpeg/png/gif/bmp）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args(argv)
    _setup_stdio()
    rows = [analyze(p) for p in collect_paths(args.paths)]
    if not rows:
        print("没有找到可检查的图片文件。")
        return 0
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print_report(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
