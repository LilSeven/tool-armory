#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按尺寸档位生成图片归类移动方案（img-sort-by-dims / 按尺寸档归类）。

用途：
    扫描目录顶层的图片，直接解析文件头获取真实像素尺寸（无需 Pillow），
    按最长边 max(宽, 高) 分为 ≥4K / 2K / HD / 小图 四档，输出"应移动到
    哪个子目录"的归类方案。默认只出方案，不移动任何文件。

档位（按最长边）：
    ≥4K : >= 3840        -> <目录>/4K/
    2K  : 2560 ~ 3839    -> <目录>/2K/
    HD  : 1280 ~ 2559    -> <目录>/HD/
    小图 : < 1280        -> <目录>/small/
阈值可用 --4k / --2k / --hd 调整。

支持格式：PNG / JPEG / GIF / BMP / WebP。只扫描目录顶层，不递归。

示例命令：
    python img-sort-by-dims.py D:/pics            # 打印归类方案
    python img-sort-by-dims.py D:/pics --json     # JSON 方案
    python img-sort-by-dims.py D:/pics --shell    # 打印可粘贴的 mv 命令
    python img-sort-by-dims.py D:/pics --apply    # 真正建档位目录并移动
    python img-sort-by-dims.py D:/pics --4k 4096  # 自定义 ≥4K 阈值

退出码：0 成功；1 目录不存在；2 参数错误。
"""
import argparse
import json
import os
import shutil
import struct
import sys

EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
TIER_DIR = {"≥4K": "4K", "2K": "2K", "HD": "HD", "小图": "small"}
TIER_ORDER = ["≥4K", "2K", "HD", "小图"]


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


def classify(w, h, t4k, t2k, thd):
    long_side = max(w, h)
    if long_side >= t4k:
        return "≥4K"
    if long_side >= t2k:
        return "2K"
    if long_side >= thd:
        return "HD"
    return "小图"


def _bash_quote(p):
    return '"' + p.replace(os.sep, "/") + '"'


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="按尺寸档位（≥4K/2K/HD/小图）生成图片归类移动方案")
    ap.add_argument("directory", help="待归类的图片目录（只扫描顶层）")
    ap.add_argument("--4k", dest="t4k", type=int, default=3840, metavar="N",
                    help="≥4K 档阈值（默认 3840）")
    ap.add_argument("--2k", dest="t2k", type=int, default=2560, metavar="N",
                    help="2K 档阈值（默认 2560）")
    ap.add_argument("--hd", dest="thd", type=int, default=1280, metavar="N",
                    help="HD 档阈值（默认 1280）")
    ap.add_argument("--shell", action="store_true",
                    help="输出可粘贴到 Git Bash 的 mv 命令")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出方案")
    ap.add_argument("--apply", action="store_true",
                    help="执行方案：创建档位子目录并移动文件（默认只出方案）")
    args = ap.parse_args(argv)

    root = args.directory
    if not os.path.isdir(root):
        print("错误：目录不存在：%s" % root, file=sys.stderr)
        return 1

    items, errors = [], []
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if not os.path.isfile(p):
            continue
        if os.path.splitext(name)[1].lower() not in EXTS:
            continue
        try:
            w, h = probe_size(p)
        except Exception as exc:
            errors.append({"file": name, "error": str(exc)})
            continue
        tier = classify(w, h, args.t4k, args.t2k, args.thd)
        items.append({"file": name, "src": p, "width": w, "height": h,
                      "tier": tier,
                      "dest": os.path.join(root, TIER_DIR[tier], name)})

    if args.json:
        counts = {t: 0 for t in TIER_ORDER}
        for it in items:
            counts[it["tier"]] += 1
        print(json.dumps({"root": root,
                          "thresholds": {"4k": args.t4k, "2k": args.t2k,
                                         "hd": args.thd},
                          "items": items, "counts": counts, "errors": errors},
                         ensure_ascii=False, indent=2))
        return 0

    if args.shell:
        for it in items:
            print("mv %s %s" % (_bash_quote(it["src"]), _bash_quote(it["dest"])))
        for e in errors:
            print("# 无法解析，未列入方案：%s（%s）" % (e["file"], e["error"]),
                  file=sys.stderr)
        return 0

    if args.apply:
        moved = skipped = 0
        for it in items:
            try:
                os.makedirs(os.path.dirname(it["dest"]), exist_ok=True)
                if os.path.exists(it["dest"]):
                    print("!! 目标已存在，跳过：%s" % it["dest"], file=sys.stderr)
                    skipped += 1
                    continue
                shutil.move(it["src"], it["dest"])
                print("已移动：%s -> %s/" % (it["file"], TIER_DIR[it["tier"]]))
                moved += 1
            except OSError as exc:
                print("!! 移动失败：%s（%s）" % (it["file"], exc), file=sys.stderr)
                skipped += 1
        print("完成：移动 %d 张，跳过/失败 %d 张，未识别 %d 张"
              % (moved, skipped, len(errors)))
        return 0

    # 默认：打印表格方案
    if not items and not errors:
        print("目录中没有图片文件：%s" % root)
        return 0
    for tier in TIER_ORDER:
        rows = [it for it in items if it["tier"] == tier]
        if not rows:
            continue
        print("== %s  ->  %s/" % (tier, TIER_DIR[tier]))
        for it in rows:
            print("   %dx%d  %s" % (it["width"], it["height"], it["file"]))
    for e in errors:
        print("!! 无法解析：%s（%s）" % (e["file"], e["error"]), file=sys.stderr)
    counts = {t: 0 for t in TIER_ORDER}
    for it in items:
        counts[it["tier"]] += 1
    print("汇总：%s；未识别 %d；共 %d 张" % (
        "、".join("%s %d 张" % (t, counts[t]) for t in TIER_ORDER if counts[t]),
        len(errors), len(items)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
