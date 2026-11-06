#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""img-format-id —— 仅凭文件头魔数识别图片格式,并给出命中字节依据。

不受扩展名影响:把 PNG 改名成 .txt 也能凭字节证据识别。每条规则给出
置信度(high/medium/low)与证据(文件偏移 + 十六进制字节 + 含义)。

支持: PNG、GIF、JPEG、TIFF、WEBP、ICO、CUR、PSD、JPEG 2000(JP2)、DDS、
GIMP XCF、PNM(P1~P7)、BMP、XPM、TGA(2.0 尾部签名)、HEIC/HEIF/AVIF
(ftyp 品牌)、XBM(启发式)、SVG(启发式)、PCX(启发式)。仅用 Python 标准库。

用法:
    python img-format-id.py [--json] FILE [FILE ...]

示例:
    python img-format-id.py mystery.dat            # 输出格式、置信度与字节证据
    python img-format-id.py --json *.bin           # JSON 数组输出
    cat header.bin | python img-format-id.py -     # 从标准输入读

输出(文本模式):
    t.png: PNG 置信度=高
      @0x00000000 (8 字节): 89 50 4E 47 0D 0A 1A 0A — PNG 文件签名

退出码: 0 全部识别;1 至少一个未识别;2 存在读取失败。
"""

import argparse
import glob
import json
import re
import sys

FTYP_BRANDS = {
    b"heic": "HEIC", b"heix": "HEIC", b"hevc": "HEIC(图像序列)",
    b"mif1": "HEIF", b"mif2": "HEIF", b"msf1": "HEIF(图像序列)",
    b"avif": "AVIF", b"avis": "AVIF(图像序列)",
}

PNM_MAGICS = (b"P1", b"P2", b"P3", b"P4", b"P5", b"P6", b"P7")
WS = b" \t\r\n\x0b\x0c"


def setup_stdio():
    """Windows 管道/重定向下强制 UTF-8 输出,避免 GBK 编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


# ---------- 规则函数:命中返回 (格式名, 置信度, [(偏移, 字节数, 说明), ...]) ----------

def rule_png(d):
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return "PNG", "high", [(0, 8, "PNG 文件签名")]


def rule_gif(d):
    if d[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    return d[:6].decode("ascii"), "high", [(0, 6, "GIF 版本标识")]


def rule_jp2(d):
    if d[:12] != b"\x00\x00\x00\x0cjP  \x0d\x0a\x87\x0a":
        return None
    return "JPEG2000(JP2)", "high", [(0, 12, "JPEG 2000 签名框")]


def rule_tiff(d):
    if d[:4] == b"II\x2a\x00":
        return "TIFF", "high", [(0, 4, "II 小端序 + 魔数 42")]
    if d[:4] == b"MM\x00\x2a":
        return "TIFF", "high", [(0, 4, "MM 大端序 + 魔数 42")]
    return None


def rule_webp(d):
    if d[:4] == b"RIFF" and d[8:12] == b"WEBP":
        return "WEBP", "high", [(0, 4, "RIFF 容器标识"), (8, 4, "WEBP 子格式标识")]
    return None


def rule_psd(d):
    if d[:4] == b"8BPS":
        return "PSD", "high", [(0, 4, "Photoshop 文件标识 8BPS")]
    return None


def rule_dds(d):
    if d[:4] == b"DDS ":
        return "DDS", "high", [(0, 4, "DirectDraw Surface 标识")]
    return None


def rule_xcf(d):
    if d[:9] == b"gimp xcf ":
        return "XCF", "high", [(0, 9, "GIMP XCF 标识")]
    return None


def rule_ftyp(d):
    if len(d) < 12 or d[4:8] != b"ftyp":
        return None
    brand = d[8:12]
    name = FTYP_BRANDS.get(brand)
    if name is None:
        return None
    return name, "high", [(4, 4, "ISOBMFF ftyp 框类型"),
                          (8, 4, "主要品牌 %s" % brand.decode("latin-1"))]


def rule_pnm(d):
    if len(d) < 3 or d[:2] not in PNM_MAGICS:
        return None
    if d[2:3] not in (b" ", b"\t", b"\r", b"\n", b"\x0b", b"\x0c"):
        return None
    return "PNM(P%s)" % d[1:2].decode("ascii"), "high", \
        [(0, 2, "PNM 魔数 P%s" % d[1:2].decode("ascii"))]


def rule_jpeg(d):
    if d[:3] != b"\xff\xd8\xff":
        return None
    return "JPEG", "high", [(0, 3, "SOI(FFD8)+ 起始标记字节")]


def rule_bmp(d):
    if d[:2] != b"BM":
        return None
    if len(d) >= 18:
        dib = int.from_bytes(d[14:18], "little")
        if dib in (12, 40, 52, 56, 64, 108, 124):
            return "BMP", "high", [(0, 2, "BM 标识"),
                                   (14, 4, "DIB 头大小 %d" % dib)]
    return "BMP", "low", [(0, 2, "BM 标识,但 DIB 头大小异常(疑似)")]


def rule_xpm(d):
    if d[:9] == b"/* XPM */":
        return "XPM", "high", [(0, 9, "XPM 固定注释头")]
    return None


def rule_tga(d):
    if len(d) >= 18 and d[-18:] == b"TRUEVISION-XFILE.\x00":
        return "TGA", "medium", [(len(d) - 18, 18, "TGA 2.0 尾部签名")]
    return None


def rule_ico(d):
    if d[:4] == b"\x00\x00\x01\x00":
        return "ICO", "medium", [(0, 4, "保留字 0x0000 + 类型 0x0001(图标);"
                                        "与无调色板 TGA 头部有固有二义性")]
    return None


def rule_cur(d):
    if d[:4] == b"\x00\x00\x02\x00":
        return "CUR", "medium", [(0, 4, "保留字 0x0000 + 类型 0x0002(光标);"
                                        "与无调色板 TGA 头部有固有二义性")]
    return None


def rule_xbm(d):
    head = d[:512]
    if not head.lstrip().startswith(b"#define"):
        return None
    m = re.search(rb"#define\s+\S*?width\s+\d+", head)
    if not m:
        return None
    return "XBM", "low", [(m.start(), 7, "#define 文本特征(启发式)")]


def rule_svg(d):
    head = d[:2048]
    i = 0
    while i < len(head) and head[i] in WS:
        i += 1
    if head[i:i + 5] == b"<?xml":
        pos = head.find(b"<svg")
        if pos != -1:
            return "SVG", "low", [(0, 5, "XML 声明(启发式)"),
                                  (pos, 4, "<svg 根元素标签")]
    if head[i:i + 4] == b"<svg":
        return "SVG", "medium", [(i, 4, "<svg 根元素标签")]
    return None


def rule_pcx(d):
    if len(d) >= 128 and d[0] == 0x0A and d[1] <= 5 and d[2] in (0, 1):
        return "PCX", "low", [(0, 3, "PCX 制造商/版本/编码字节弱特征(启发式)")]
    return None


# 顺序即优先级:精确魔数在前,启发式与有二义性的在后
RULES = (rule_png, rule_gif, rule_jp2, rule_tiff, rule_webp, rule_psd,
         rule_dds, rule_xcf, rule_ftyp, rule_pnm, rule_jpeg, rule_bmp,
         rule_xpm, rule_tga, rule_ico, rule_cur, rule_xbm, rule_svg, rule_pcx)

CONF_ZH = {"high": "高", "medium": "中", "low": "低(启发式)"}


def identify(data):
    for rule in RULES:
        hit = rule(data)
        if hit:
            name, conf, evlist = hit
            evidence = []
            for off, length, note in evlist:
                raw = data[off:off + length]
                hexs = " ".join("%02X" % b for b in raw)
                evidence.append({"offset": off, "length": length,
                                 "hex": hexs, "note": note})
            return {"format": name, "confidence": conf, "evidence": evidence}
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
        prog="img-format-id.py",
        description="仅凭文件头魔数识别图片格式并给出字节依据,不受扩展名影响(详见文件顶部 docstring)。",
    )
    ap.add_argument("files", nargs="*", metavar="FILE",
                    help="待识别文件,支持通配符;'-' 表示标准输入")
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
            rec = {"file": name}
            rec.update(hit)
            results.append(rec)
        else:
            results.append({"file": name, "format": None})
            any_unknown = True

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for rec in results:
            if rec.get("error"):
                print("%s: 读取失败(%s)" % (rec["file"], rec["error"]))
            elif rec["format"] is None:
                print("%s: 未知(没有规则命中)" % rec["file"])
            else:
                print("%s: %s 置信度=%s"
                      % (rec["file"], rec["format"],
                         CONF_ZH.get(rec["confidence"], rec["confidence"])))
                for e in rec["evidence"]:
                    print("  @0x%08X (%d 字节): %s — %s"
                          % (e["offset"], e["length"], e["hex"], e["note"]))
    return 2 if any_failed else (1 if any_unknown else 0)


if __name__ == "__main__":
    sys.exit(main())
