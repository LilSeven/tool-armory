#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gif-header-dump —— 解析并转储 GIF 头部(逻辑屏幕描述符)。

输出 GIF 版本号(GIF87a/GIF89a)、逻辑屏幕宽高、全局调色板有无与规模
(2^(N+1) 色)、颜色分辨率位、调色板排序位、背景色索引、像素宽高比字段
及其换算比值(=(N+15)/64,N 为 0 时视为未指定);并检查头部/调色板是否
被截断、提示紧跟的下一个数据块类型。仅用 Python 标准库。

用法:
    python gif-header-dump.py [--json] FILE [FILE ...]

示例:
    python gif-header-dump.py anim.gif
    python gif-header-dump.py --json banner.gif

退出码: 0 全部解析成功;1 存在魔数不符(非 GIF);2 存在截断或读取失败。
"""

import argparse
import glob
import json
import sys

NEXT_BLOCK = {0x21: "扩展块(0x21)", 0x2C: "图像描述符(0x2C)", 0x3B: "流结束(0x3B)"}


def setup_stdio():
    """Windows 管道/重定向下强制 UTF-8 输出,避免 GBK 编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def parse_gif(data):
    """成功返回 (info_dict, warnings, None);失败返回 (None, [], 错误说明)。"""
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        return None, [], "不是 GIF:版本字段=%r(应为 GIF87a/GIF89a)" % data[:6]
    if len(data) < 13:
        return None, [], "文件过短(%d 字节),头部+逻辑屏幕描述符需 13 字节" % len(data)

    w = int.from_bytes(data[6:8], "little")
    h = int.from_bytes(data[8:10], "little")
    packed = data[10]
    gct_flag = bool(packed & 0x80)
    color_res = (packed >> 4) & 0x07
    sort_flag = bool(packed & 0x08)
    gct_bits = packed & 0x07
    gct_colors = (1 << (gct_bits + 1)) if gct_flag else 0
    bg = data[11]
    aspect = data[12]

    info = {"version": data[:6].decode("ascii"), "width": w, "height": h,
            "packed_field": "0x%02X" % packed,
            "global_palette": gct_flag,
            "global_palette_colors": gct_colors,
            "global_palette_bytes": gct_colors * 3,
            "color_resolution_bits": color_res,
            "color_resolution_primaries": color_res + 1,
            "global_palette_sorted": sort_flag,
            "background_index": bg,
            "pixel_aspect_ratio_field": aspect,
            "header_and_palette_bytes": 13 + gct_colors * 3,
            "file_size_actual": len(data)}
    if aspect:
        info["pixel_aspect_ratio_value"] = round((aspect + 15) / 64.0, 4)

    warnings = []
    need = info["header_and_palette_bytes"]
    if len(data) < need:
        return None, [], ("截断:头部+全局调色板需 %d 字节,文件仅 %d 字节"
                          % (need, len(data)))
    if gct_flag and bg >= gct_colors:
        warnings.append("背景色索引 %d 超出全局调色板规模(%d 色)" % (bg, gct_colors))
    if len(data) > need:
        nxt = data[need]
        info["next_block"] = {"offset": need, "byte": "0x%02X" % nxt,
                              "meaning": NEXT_BLOCK.get(nxt, "未知块类型")}
    return info, warnings, None


def render(rec):
    lines = ["文件: %s (%d 字节)" % (rec["file"], rec["file_size_actual"])]
    lines.append("  版本: %s" % rec["version"])
    lines.append("  逻辑屏幕: 宽 %d x 高 %d 像素" % (rec["width"], rec["height"]))
    if rec["global_palette"]:
        lines.append("  全局调色板: 有 — %d 色(需 %d 字节)"
                     % (rec["global_palette_colors"], rec["global_palette_bytes"]))
    else:
        lines.append("  全局调色板: 无")
    lines.append("  颜色分辨率位: %d → 每原色 %d 位"
                 % (rec["color_resolution_bits"], rec["color_resolution_primaries"]))
    lines.append("  全局调色板排序: %s" % ("是" if rec["global_palette_sorted"] else "否"))
    lines.append("  背景色索引: %d" % rec["background_index"])
    if "pixel_aspect_ratio_value" in rec:
        lines.append("  像素宽高比: 字段=%d → 比值 %.4f"
                     % (rec["pixel_aspect_ratio_field"], rec["pixel_aspect_ratio_value"]))
    else:
        lines.append("  像素宽高比: 字段=%d → 未指定(按 1:1)"
                     % rec["pixel_aspect_ratio_field"])
    lines.append("  packed 字段: %s" % rec["packed_field"])
    if "next_block" in rec:
        nb = rec["next_block"]
        lines.append("  下一块 @偏移 %d: 字节 %s → %s"
                     % (nb["offset"], nb["byte"], nb["meaning"]))
    for wmsg in rec["warnings"]:
        lines.append("  [警告] " + wmsg)
    return "\n".join(lines)


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
        prog="gif-header-dump.py",
        description="解析 GIF 逻辑屏幕描述符并转储(详见文件顶部 docstring)。",
    )
    ap.add_argument("files", nargs="+", metavar="FILE", help="GIF 文件,支持通配符")
    ap.add_argument("--json", action="store_true", help="以 JSON 数组输出")
    args = ap.parse_args(argv)

    results, any_notgif, any_broken = [], False, False
    for path in expand_inputs(args.files):
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            results.append({"file": path, "error": str(exc)})
            any_broken = True
            continue
        info, warnings, fatal = parse_gif(data)
        if info is None:
            results.append({"file": path, "error": fatal})
            if fatal.startswith("不是 GIF"):
                any_notgif = True
            else:
                any_broken = True
        else:
            rec = {"file": path}
            rec.update(info)
            rec["warnings"] = warnings
            results.append(rec)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for rec in results:
            if "version" not in rec:
                print("%s: 解析失败(%s)" % (rec["file"], rec["error"]))
            else:
                print(render(rec))
    return 2 if any_broken else (1 if any_notgif else 0)


if __name__ == "__main__":
    sys.exit(main())
