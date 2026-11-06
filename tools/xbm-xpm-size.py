#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XBM/XPM 尺寸读取器(xbm-xpm-size) —— 从 XBM 的 C 宏定义或 XPM 的字符串数组中解析位图宽高。

用途:
    自动识别并解析两种古老的位图格式：
    1. XBM(X11 bitmap)：从 "#define <name>_width N" / "_height" 宏对取宽高，
       若存在 "_x_hot"/"_y_hot" 一并报告热点；
    2. XPM/XPM2(X pixmap)：从数组首行(或 XPM2 的独立行)尺寸串
       "W H Ncolors Ncpp [xhot yhot]" 取宽高、颜色数与每像素字符数。

用法:
    python xbm-xpm-size.py <file.xbm|file.xpm> [--json]
    python xbm-xpm-size.py --make-sample <out.xbm|.xpm|.xpm2>   生成示例文件
    python xbm-xpm-size.py --selftest                           构造示例输入并自校验

示例:
    python xbm-xpm-size.py cursor.xbm
    python xbm-xpm-size.py icon.xpm --json
    python xbm-xpm-size.py --make-sample demo.xbm
    python xbm-xpm-size.py --selftest

退出码: 0=成功; 1=两种格式都解析不出来; 2=命令行用法错误。
仅使用 Python 标准库(argparse/json/re/tempfile/os)。
"""

import argparse
import json
import os
import re
import sys
import tempfile

DEFINE_RE = re.compile(r"#\s*define\s+([A-Za-z_]\w*)\s+(\d+)\b", re.IGNORECASE)
XPM_MARKER_RE = re.compile(r"/\*\s*XPM\s*\*/")
XPM2_MARKER_RE = re.compile(r"^\s*!\s*XPM2\b", re.MULTILINE)
XPM_VALUES_RE = re.compile(
    r'"\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)(?:\s+(\d+)\s+(\d+))?\s*"')
XPM2_VALUES_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)(?:\s+(\d+)\s+(\d+))?\s*$", re.MULTILINE)

XBM_SUFFIXES = (("_width", "width"), ("_height", "height"),
                ("_x_hot", "x_hot"), ("_y_hot", "y_hot"))


class SizeError(ValueError):
    """解析失败。"""


def parse_xbm(text):
    """从 #define 宏对提取宽高；找不到配对的 width/height 时返回 None。"""
    defs = {}
    for name, value in DEFINE_RE.findall(text):
        low = name.lower()
        for suffix, key in XBM_SUFFIXES:
            if low.endswith(suffix):
                defs.setdefault(low[:-len(suffix)], {})[key] = int(value)
                break
    for name in sorted(defs):
        fields = defs[name]
        if "width" in fields and "height" in fields:
            hotspot = None
            if "x_hot" in fields and "y_hot" in fields:
                hotspot = (fields["x_hot"], fields["y_hot"])
            return {"format": "XBM", "name": name,
                    "width": fields["width"], "height": fields["height"],
                    "hotspot": hotspot}
    return None


def xpm_from_match(match, fmt):
    width, height, colors, cpp = (int(match.group(i)) for i in range(1, 5))
    hotspot = None
    if match.group(5) is not None and match.group(6) is not None:
        hotspot = (int(match.group(5)), int(match.group(6)))
    return {"format": fmt, "width": width, "height": height,
            "colors": colors, "chars_per_pixel": cpp, "hotspot": hotspot}


def parse_xpm3(text):
    match = XPM_VALUES_RE.search(text)
    return xpm_from_match(match, "XPM (XPM3)") if match else None


def parse_xpm2(text):
    match = XPM2_VALUES_RE.search(text)
    return xpm_from_match(match, "XPM2") if match else None


def parse(text):
    """自动识别 XBM / XPM3 / XPM2，返回信息 dict；失败抛 SizeError。"""
    if XPM2_MARKER_RE.search(text):
        info = parse_xpm2(text)
        if info:
            return info
    info = parse_xbm(text)
    if info:
        return info
    if XPM_MARKER_RE.search(text):
        info = parse_xpm3(text)
        if info:
            return info
    info = parse_xpm3(text)  # 兜底：没有 /* XPM */ 标记也尝试首个 "W H N C" 串
    if info:
        info["format"] = "XPM (no marker)"
        return info
    raise SizeError("no XBM #define _width/_height pair and no XPM size string found")


def parse_bytes(blob):
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        text = blob.decode("latin-1")
    return parse(text)


def format_text(info):
    lines = [
        "file: %s" % info.get("path", "<memory>"),
        "format: %s" % info["format"],
        "width x height: %d x %d" % (info["width"], info["height"]),
    ]
    if "name" in info:
        lines.append("name: %s" % info["name"])
    if "colors" in info:
        lines.append("colors: %d  chars_per_pixel: %d"
                     % (info["colors"], info["chars_per_pixel"]))
    if info.get("hotspot"):
        lines.append("hotspot: x=%d y=%d" % info["hotspot"])
    return "\n".join(lines)


XBM_SAMPLE = """\
#define invader_width 12
#define invader_height 8
#define invader_x_hot 5
#define invader_y_hot 3
static unsigned char invader_bits[] = {
   0x7c, 0x00, 0xfe, 0x00, 0xff, 0x01, 0xdf, 0x01,
   0x7c, 0x00, 0x38, 0x00, 0xee, 0x00, 0x00, 0x00 };
"""

XPM_SAMPLE = """\
/* XPM */
static char * dot_xpm[] = {
"11 7 2 1 3 2",
"* c #000000",
". c #FFFFFF",
"*....*....*",
".....*.....",
"*....*....*",
"...........",
"*....*....*",
".....*.....",
"*....*....*"
};
"""

XPM2_SAMPLE = ("! XPM2\n"
               "8 6 2 1\n"
               "# c #000000\n"
               ". c #FFFFFF\n"
               "#..#..#.\n"
               "....#...\n"
               "#..#..#.\n"
               "........\n"
               "#..#..#.\n"
               "....#...\n")


def make_sample(path):
    """按扩展名生成示例：.xpm -> XPM3，.xpm2 -> XPM2，其余 -> XBM。"""
    low = str(path).lower()
    if low.endswith(".xpm"):
        return XPM_SAMPLE.encode("utf-8")
    if low.endswith(".xpm2"):
        return XPM2_SAMPLE.encode("utf-8")
    return XBM_SAMPLE.encode("utf-8")


def selftest():
    # 1) XBM：宽高 + 热点
    info = parse(XBM_SAMPLE)
    assert (info["width"], info["height"]) == (12, 8), info
    assert info["name"] == "invader" and info["hotspot"] == (5, 3), info
    print("  [ok] XBM 12x8 with hot spot (5,3)")

    # 2) XPM3：尺寸 + 颜色数 + 每像素字符数 + 热点
    info = parse(XPM_SAMPLE)
    assert (info["width"], info["height"]) == (11, 7), info
    assert (info["colors"], info["chars_per_pixel"]) == (2, 1), info
    assert info["hotspot"] == (3, 2), info
    print("  [ok] XPM3 11x7, 2 colors, cpp 1, hot spot (3,2)")

    # 3) XPM2
    info = parse(XPM2_SAMPLE)
    assert info["format"] == "XPM2" and (info["width"], info["height"]) == (8, 6), info
    print("  [ok] XPM2 8x6")

    # 4) 解析不出的输入必须报错
    for bad in ("hello world", "#define foo_width 4\n"):
        try:
            parse(bad)
        except SizeError:
            pass
        else:
            raise AssertionError("bad input accepted: %r" % bad[:20])
    print("  [ok] unparseable text rejected (missing height / no defines)")

    # 5) 临时文件链路（XBM 与 XPM 各一遍）+ 文本/JSON 输出
    for suffix, sample, expect in ((".xbm", XBM_SAMPLE, (12, 8)),
                                   (".xpm", XPM_SAMPLE, (11, 7))):
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False,
                                         mode="w", encoding="utf-8") as fh:
            fh.write(sample)
            path = fh.name
        try:
            with open(path, "rb") as fh:
                info = parse_bytes(fh.read())
            assert (info["width"], info["height"]) == expect, info
            assert str(expect[0]) in format_text(dict(info, path=path))
            assert json.loads(json.dumps(info))["width"] == expect[0]
        finally:
            os.unlink(path)
    print("  [ok] temp-file round-trip for XBM and XPM, text+json output")

    print("selftest PASS (5 checks)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="xbm-xpm-size",
        description="从 XBM 的 C 宏定义或 XPM 的字符串数组中解析位图宽高")
    parser.add_argument("file", nargs="?", help=".xbm/.xpm 文件路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--make-sample", metavar="OUT",
                        help="生成示例文件(按扩展名 .xpm/.xpm2/.xbm 选择格式)后退出")
    parser.add_argument("--selftest", action="store_true", help="运行内置自测后退出")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.make_sample:
        blob = make_sample(args.make_sample)
        with open(args.make_sample, "wb") as fh:
            fh.write(blob)
        print("wrote %d-byte sample to %s" % (len(blob), args.make_sample))
        return 0
    if not args.file:
        parser.error("need an .xbm/.xpm file (or --selftest / --make-sample)")
    try:
        with open(args.file, "rb") as fh:
            info = parse_bytes(fh.read())
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    except SizeError as exc:
        print("error: %s: %s" % (args.file, exc), file=sys.stderr)
        return 1
    info["path"] = args.file
    print(json.dumps(info, indent=2) if args.json else format_text(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
