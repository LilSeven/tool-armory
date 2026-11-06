#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""目录尺寸差异对比（img-dir-diff）。

用途：
    递归收集两个目录中的同名图片（按相对路径匹配，忽略大小写），解析
    文件头比较像素尺寸，标出尺寸不一致的项；同时列出仅存在于其中一侧的
    文件和解析失败的文件。只读文件头，不修改任何文件。

支持格式：PNG / JPEG / GIF / BMP / WebP。

示例命令：
    python img-dir-diff.py D:/pics_a D:/pics_b
    python img-dir-diff.py D:/pics_a D:/pics_b --json

退出码：0 两个目录完全一致（同名图片尺寸相同且无单侧缺失）；
        1 存在差异（尺寸不一致 / 单侧缺失 / 解析失败）；
        2 目录不存在或参数错误。
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


def scan_dir(root):
    """返回 {相对路径(小写): ("ok",(w,h)) 或 ("error",说明)}。"""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            if os.path.splitext(name)[1].lower() not in EXTS:
                continue
            p = os.path.join(dirpath, name)
            rel = os.path.relpath(p, root).replace(os.sep, "/").lower()
            try:
                w, h = probe_size(p)
                out[rel] = ("ok", (w, h))
            except Exception as exc:
                out[rel] = ("error", str(exc))
    return out


def _fmt_state(st):
    if st[0] == "ok":
        return "%dx%d" % st[1]
    return "解析失败(%s)" % st[1]


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="对比两个目录中同名图片的尺寸差异，标出不一致项")
    ap.add_argument("dir_a", help="目录 A")
    ap.add_argument("dir_b", help="目录 B")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = ap.parse_args(argv)

    for d in (args.dir_a, args.dir_b):
        if not os.path.isdir(d):
            print("错误：目录不存在：%s" % d, file=sys.stderr)
            return 2

    a_map = scan_dir(args.dir_a)
    b_map = scan_dir(args.dir_b)
    common = sorted(set(a_map) & set(b_map))
    only_a = sorted(set(a_map) - set(b_map))
    only_b = sorted(set(b_map) - set(a_map))

    same_rows, mismatch_rows, error_rows = [], [], []
    for rel in common:
        ka, kb = a_map[rel], b_map[rel]
        if ka[0] == "ok" and kb[0] == "ok":
            if ka[1] == kb[1]:
                same_rows.append({"name": rel, "a": list(ka[1]), "b": list(kb[1])})
            else:
                mismatch_rows.append({"name": rel, "a": list(ka[1]), "b": list(kb[1])})
        else:
            error_rows.append({"name": rel, "a": _fmt_state(ka), "b": _fmt_state(kb)})

    has_diff = bool(mismatch_rows or error_rows or only_a or only_b)

    if args.json:
        print(json.dumps({
            "a": args.dir_a, "b": args.dir_b,
            "mismatch": mismatch_rows,
            "errors": error_rows,
            "same": same_rows,
            "only_in_a": only_a,
            "only_in_b": only_b,
            "counts": {"same": len(same_rows), "mismatch": len(mismatch_rows),
                       "errors": len(error_rows), "only_in_a": len(only_a),
                       "only_in_b": len(only_b)},
        }, ensure_ascii=False, indent=2))
        return 1 if has_diff else 0

    print("A = %s" % os.path.abspath(args.dir_a))
    print("B = %s" % os.path.abspath(args.dir_b))
    print("-- 尺寸不一致（%d）--" % len(mismatch_rows))
    for r in mismatch_rows:
        print("  %-40s A: %dx%d   B: %dx%d"
              % (r["name"], r["a"][0], r["a"][1], r["b"][0], r["b"][1]))
    print("-- 解析失败（%d）--" % len(error_rows))
    for r in error_rows:
        print("  %-40s A: %s   B: %s" % (r["name"], r["a"], r["b"]))
    print("-- 仅在 A（%d）--" % len(only_a))
    for rel in only_a:
        print("  " + rel)
    print("-- 仅在 B（%d）--" % len(only_b))
    for rel in only_b:
        print("  " + rel)
    print("-- 一致（%d）--" % len(same_rows))
    for r in same_rows:
        print("  %-40s %dx%d" % (r["name"], r["a"][0], r["a"][1]))
    print("汇总：一致 %d，尺寸不一致 %d，解析失败 %d，仅A %d，仅B %d"
          % (len(same_rows), len(mismatch_rows), len(error_rows),
             len(only_a), len(only_b)))
    return 1 if has_diff else 0


if __name__ == "__main__":
    sys.exit(main())
