#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""img-size-probe —— 万能图片尺寸探测(imghdr 被移除后的现代替代)。

Python 3.13 起标准库移除了 imghdr 模块。本工具仅凭文件头解析常见图片格式
的像素尺寸,不受文件扩展名影响,并报告命中了哪个解析器。仅用 Python 标准库。

支持: PNG、GIF、BMP、JPEG(SOF0~SOF15)、TIFF(II/MM)、PNM(P1~P6 及 P7/PAM)、
ICO、CUR、WEBP(VP8/VP8L/VP8X)、PSD、XBM(启发式)、TGA(带 2.0 尾部签名时)。
注意: ICO/CUR 与无调色板 TGA 的头部存在固有二义性,优先按 TGA 尾部签名判定。

用法:
    python img-size-probe.py [--json] FILE [FILE ...]

示例:
    python img-size-probe.py photo.jpg icon.png     # 逐文件输出宽高与解析器
    python img-size-probe.py --json *.png           # 机器可读 JSON 数组
    python img-size-probe.py - < mystery.bin        # 从标准输入读字节

输出(文本模式,每行一个文件):
    photo.jpg: 格式=JPEG 宽=1920 高=1080 解析器=jpeg (SOF 标记 0xC0)
    mystery.bin: 未知(没有任何解析器命中)

退出码: 0 全部识别出尺寸;1 至少一个文件未识别;2 存在读取失败。
"""

import argparse
import glob
import json
import re
import sys

SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
               0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def setup_stdio():
    """Windows 管道/重定向下强制 UTF-8 输出,避免 GBK 编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


# ---------- 探测函数:命中返回 (宽, 高, 解析器名, 依据说明),否则返回 None ----------

def probe_png(d):
    if d[:8] != b"\x89PNG\r\n\x1a\n" or d[12:16] != b"IHDR" or len(d) < 24:
        return None
    return (int.from_bytes(d[16:20], "big"), int.from_bytes(d[20:24], "big"),
            "png", "PNG IHDR 块")


def probe_gif(d):
    if d[:6] not in (b"GIF87a", b"GIF89a") or len(d) < 10:
        return None
    return (int.from_bytes(d[6:8], "little"), int.from_bytes(d[8:10], "little"),
            "gif", "%s 逻辑屏幕描述符" % d[:6].decode("ascii"))


def probe_bmp(d):
    if d[:2] != b"BM" or len(d) < 26:
        return None
    w = int.from_bytes(d[18:22], "little", signed=True)
    h = int.from_bytes(d[22:26], "little", signed=True)
    return (abs(w), abs(h), "bmp",
            "DIB 宽高字段(高度%s)" % ("负值=自顶向下" if h < 0 else "正值=自底向上"))


def probe_tiff(d):
    if d[:2] == b"II" and d[2:4] == b"\x2a\x00":
        en, ename = "little", "II 小端"
    elif d[:2] == b"MM" and d[2:4] == b"\x00\x2a":
        en, ename = "big", "MM 大端"
    else:
        return None
    if len(d) < 8:
        return None
    ifd = int.from_bytes(d[4:8], en)
    if ifd + 2 > len(d):
        return None
    cnt = int.from_bytes(d[ifd:ifd + 2], en)
    w = h = None
    for k in range(cnt):
        off = ifd + 2 + 12 * k
        if off + 12 > len(d):
            return None
        tag = int.from_bytes(d[off:off + 2], en)
        typ = int.from_bytes(d[off + 2:off + 4], en)
        if tag not in (256, 257):
            continue
        if typ == 3:      # SHORT:值位于值字段前 2 字节
            val = int.from_bytes(d[off + 8:off + 10], en)
        elif typ == 4:    # LONG
            val = int.from_bytes(d[off + 8:off + 12], en)
        else:
            continue
        if tag == 256:
            w = val
        else:
            h = val
    if w is None or h is None:
        return None
    return w, h, "tiff", "IFD0 tag256/257(%s)" % ename


def probe_jpeg(d):
    if d[:3] != b"\xff\xd8\xff":
        return None
    n, i = len(d), 2
    while i < n:
        if d[i] != 0xFF:
            return None
        j = i
        while j < n and d[j] == 0xFF:   # 0xFF 填充可连续出现
            j += 1
        if j >= n:
            return None
        marker = d[j]
        pos = j + 1                     # 长度字段起始(若该标记带长度)
        if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
            i = pos                     # 独立标记,无长度字段
            continue
        if pos + 2 > n:
            return None
        seglen = int.from_bytes(d[pos:pos + 2], "big")
        if seglen < 2:
            return None
        if marker in SOF_MARKERS:
            if pos + 7 > n:
                return None
            h = int.from_bytes(d[pos + 3:pos + 5], "big")
            w = int.from_bytes(d[pos + 5:pos + 7], "big")
            return w, h, "jpeg", "SOF 标记 0x%02X" % marker
        i = pos + seglen
    return None


def probe_pnm(d):
    if d[:2] not in (b"P1", b"P2", b"P3", b"P4", b"P5", b"P6"):
        return None
    n = min(len(d), 4096)
    i, tokens = 2, []
    ws = b" \t\r\n\x0b\x0c"
    while i < n and len(tokens) < 2:
        c = d[i]
        if c in ws:
            i += 1
        elif c == 0x23:                 # '#' 注释直到行尾
            while i < n and d[i] not in b"\r\n":
                i += 1
        else:
            j = i
            while j < n and d[j] not in ws and d[j] != 0x23:
                j += 1
            tokens.append(d[i:j])
            i = j
    if len(tokens) < 2 or not all(t.isdigit() for t in tokens):
        return None
    return int(tokens[0]), int(tokens[1]), "pnm", "%s ASCII 头" % d[:2].decode("ascii")


def probe_pam(d):
    if d[:2] != b"P7":
        return None
    head = d[:512]
    mw = re.search(rb"WIDTH\s+(\d+)", head)
    mh = re.search(rb"HEIGHT\s+(\d+)", head)
    if not (mw and mh):
        return None
    return int(mw.group(1)), int(mh.group(1)), "pnm", "PAM(P7) 头部字段"


def probe_ico(d):
    if d[:4] not in (b"\x00\x00\x01\x00", b"\x00\x00\x02\x00") or len(d) < 8:
        return None
    kind = "ico" if d[2:4] == b"\x01\x00" else "cur"
    return (d[6] or 256, d[7] or 256, kind, "目录项宽高字段(0 表示 256)")


def probe_webp(d):
    if d[:4] != b"RIFF" or d[8:12] != b"WEBP" or len(d) < 25:
        return None
    fmt = d[12:16]
    if fmt == b"VP8X":
        if len(d) < 30:
            return None
        return (1 + int.from_bytes(d[24:27], "little"),
                1 + int.from_bytes(d[27:30], "little"),
                "webp", "VP8X 扩展头 canvas 字段")
    if fmt == b"VP8 ":
        if len(d) < 30 or d[23:26] != b"\x9d\x01\x2a":
            return None
        return (int.from_bytes(d[26:28], "little") & 0x3FFF,
                int.from_bytes(d[28:30], "little") & 0x3FFF,
                "webp", "VP8 有损帧头")
    if fmt == b"VP8L":
        if d[20] != 0x2F:
            return None
        bits = int.from_bytes(d[21:25], "little")
        return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1,
                "webp", "VP8L 无损帧头")
    return None


def probe_psd(d):
    if d[:4] != b"8BPS" or len(d) < 22:
        return None
    return (int.from_bytes(d[18:22], "big"), int.from_bytes(d[14:18], "big"),
            "psd", "PSD 文件头宽/高字段")


def probe_xbm(d):
    head = d[:512]
    if not head.lstrip().startswith(b"#define"):
        return None
    mw = re.search(rb"#define\s+[\w\-\.]*?width\s+(\d+)", head)
    mh = re.search(rb"#define\s+[\w\-\.]*?height\s+(\d+)", head)
    if not (mw and mh):
        return None
    return int(mw.group(1)), int(mh.group(1)), "xbm", "#define 文本(启发式)"


def probe_tga(d):
    if len(d) < 26 or d[-18:] != b"TRUEVISION-XFILE.\x00":
        return None
    return (int.from_bytes(d[12:14], "little"), int.from_bytes(d[14:16], "little"),
            "tga", "TGA 2.0 尾部签名 + 头部宽高")


# 顺序即优先级:精确魔数在前,启发式/有二义性的在后(TGA 尾部签名优先于 ICO/CUR)
PROBES = (probe_png, probe_gif, probe_tiff, probe_webp, probe_psd,
          probe_jpeg, probe_bmp, probe_pnm, probe_pam, probe_xbm,
          probe_tga, probe_ico)


def identify(data):
    for probe in PROBES:
        hit = probe(data)
        if hit:
            w, h, parser, note = hit
            return {"format": parser, "width": w, "height": h, "note": note}
    return None


def expand_inputs(raw):
    paths = []
    for arg in raw:
        if "*" in arg or "?" in arg:
            hits = sorted(glob.glob(arg))
            if not hits:
                print("没有匹配到文件: %s" % arg, file=sys.stderr)
                raise SystemExit(2)
            paths.extend(hits)
        else:
            paths.append(arg)
    return paths


def main(argv=None):
    setup_stdio()
    ap = argparse.ArgumentParser(
        prog="img-size-probe.py",
        description="万能图片尺寸探测:仅凭文件头解析宽高,imghdr 的现代替代(详见文件顶部 docstring)。",
    )
    ap.add_argument("files", nargs="*", metavar="FILE",
                    help="待探测文件,支持通配符;'-' 表示标准输入")
    ap.add_argument("--json", action="store_true", help="以 JSON 数组输出")
    args = ap.parse_args(argv)
    if not args.files:
        ap.error("至少需要一个 FILE(可用 '-' 读标准输入)")

    results, any_unknown, any_failed = [], False, False
    for path in expand_inputs(args.files):
        if path == "-":
            data, name = sys.stdin.buffer.read(), "<stdin>"
        else:
            name = path
            try:
                with open(path, "rb") as fh:
                    data = fh.read()
            except OSError as exc:
                results.append({"file": name, "error": str(exc)})
                any_failed = True
                continue
        hit = identify(data)
        if hit:
            results.append({"file": name})
            results[-1].update(hit)
        else:
            results.append({"file": name, "format": None,
                            "width": None, "height": None})
            any_unknown = True

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for rec in results:
            if rec.get("error"):
                print("%s: 读取失败(%s)" % (rec["file"], rec["error"]))
            elif rec["format"] is None:
                print("%s: 未知(没有任何解析器命中)" % rec["file"])
            else:
                print("%s: 格式=%s 宽=%d 高=%d 解析器=%s (%s)"
                      % (rec["file"], rec["format"].upper(), rec["width"],
                         rec["height"], rec["format"], rec["note"]))
    return 2 if any_failed else (1 if any_unknown else 0)


if __name__ == "__main__":
    sys.exit(main())
