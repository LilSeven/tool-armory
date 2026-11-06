#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNM 头读取 —— 解析 PBM/PGM/PPM/PAM(P1–P7) 的魔数、宽高与最大灰度值。

支持头部注释(# 到行尾, 可出现在任意空白处)。对二进制格式(P4/P5/P6/P7)
校验头部末尾的单空白分隔符并计算预期光栅字节数; 对 P7(PAM) 解析
WIDTH/HEIGHT/DEPTH/MAXVAL/TUPLTYPE/ENDHDR 键值头。

用法:
    python pnm-header-read.py <文件.pnm> [--json]

示例:
    python pnm-header-read.py sample.pbm
    python pnm-header-read.py photo.ppm --json

退出码: 0 = 头部解析成功; 1 = 不是 PNM / 头部损坏。
仅使用 Python 标准库, 需 Python 3.7+。
"""

import argparse
import json
import sys

WS = b" \t\r\n\x0b\x0c"

# 魔数 -> (格式名, 是否二进制, 是否有 maxval 字段, 每像素样本数)
MAGIC_INFO = {
    "P1": ("便携位图 - ASCII (PBM ASCII)", False, False, 1),
    "P2": ("便携灰度图 - ASCII (PGM ASCII)", False, True, 1),
    "P3": ("便携像素图 - ASCII (PPM ASCII)", False, True, 3),
    "P4": ("便携位图 - 二进制 (PBM binary, 位打包)", True, False, 1),
    "P5": ("便携灰度图 - 二进制 (PGM binary)", True, True, 1),
    "P6": ("便携像素图 - 二进制 (PPM binary)", True, True, 3),
    "P7": ("便携任意映射 - 二进制 (PAM / Arbitrary Map)", True, True, None),
}


class ToolError(Exception):
    pass


def setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def die(msg):
    sys.stderr.write("pnm-header-read: 错误: %s\n" % msg)
    raise SystemExit(1)


def next_token(data, i):
    """跳过空白与注释, 读取一个 token; 返回 (token|None, 新位置, 途经注释数)。"""
    n = len(data)
    seen_comments = 0
    while i < n:
        c = data[i]
        if c in WS:
            i += 1
        elif c == 0x23:  # '#' 注释直到行尾
            seen_comments += 1
            while i < n and data[i] != 0x0A:
                i += 1
        else:
            break
    if i >= n:
        return None, i, seen_comments
    j = i
    while j < n and data[j] not in WS and data[j] != 0x23:
        j += 1
    return data[i:j], j, seen_comments


def find_raster_start(data, pos):
    """头部最后一个 token 之后: 允许一个注释行, 然后必须是恰好 1 个空白字节。"""
    if pos < len(data) and data[pos] == 0x23:
        while pos < len(data) and data[pos] != 0x0A:
            pos += 1
    if pos >= len(data) or data[pos] not in WS:
        raise ToolError("头部之后缺少单个空白分隔符(偏移 0x%X 处为 %r)"
                        % (pos, chr(data[pos]) if pos < len(data) else "EOF"))
    return pos + 1


def parse_plain(magic, info, data, pos, comments):
    """P1–P6: 读取 宽 高 [最大值] 三个十进制 token。"""
    _, is_binary, has_maxval, _samples = info
    toks = []
    need = 3 if has_maxval else 2
    for _ in range(need):
        tok, pos, c = next_token(data, pos)
        comments += c
        if tok is None:
            raise ToolError("%s 头不完整: 需要 %d 个数值(宽 高%s), 只读到 %d 个"
                            % (magic, need, " 最大值" if has_maxval else "", len(toks)))
        toks.append(tok)
    try:
        nums = [int(t) for t in toks]
    except ValueError:
        raise ToolError("头部数值非法: %s" % [t.decode("latin-1") for t in toks])
    width, height = nums[0], nums[1]
    maxval = nums[2] if has_maxval else 1
    if width < 1 or height < 1:
        raise ToolError("宽高必须 >= 1, 实际 %d x %d" % (width, height))
    if has_maxval and not 1 <= maxval <= 65535:
        raise ToolError("最大值 %d 超出允许范围 1-65535" % maxval)
    depth = None
    tupletype = None
    raster_off = None
    expected = None
    if is_binary:
        raster_off = find_raster_start(data, pos)
        if magic == "P4":
            expected = ((width + 7) // 8) * height
        else:
            unit = 2 if maxval > 255 else 1
            samples = 3 if magic == "P6" else 1
            expected = width * height * samples * unit
    else:
        raster_off = pos  # ASCII 格式: 头部最后一个 token 之后即为文本光栅
    return width, height, maxval, depth, tupletype, raster_off, expected, comments


def parse_pam(data, pos, comments):
    """P7 (PAM): WIDTH/HEIGHT/DEPTH/MAXVAL/TUPLTYPE ... ENDHDR。"""
    fields = {}
    while True:
        key_tok, pos, c = next_token(data, pos)
        comments += c
        if key_tok is None:
            raise ToolError("PAM 头缺少 ENDHDR")
        key = key_tok.decode("latin-1").upper()
        if key == "ENDHDR":
            break
        val_tok, pos, c2 = next_token(data, pos)
        comments += c2
        if val_tok is None:
            raise ToolError("PAM 头字段 %s 缺少值" % key)
        fields[key] = val_tok.decode("latin-1")
    missing = {"WIDTH", "HEIGHT", "DEPTH", "MAXVAL"} - set(fields)
    if missing:
        raise ToolError("PAM 头缺少必需字段: %s" % ", ".join(sorted(missing)))
    try:
        width = int(fields["WIDTH"])
        height = int(fields["HEIGHT"])
        depth = int(fields["DEPTH"])
        maxval = int(fields["MAXVAL"])
    except ValueError:
        raise ToolError("PAM 头的 WIDTH/HEIGHT/DEPTH/MAXVAL 必须是十进制整数")
    if width < 1 or height < 1:
        raise ToolError("PAM 宽高必须 >= 1, 实际 %d x %d" % (width, height))
    if depth < 1:
        raise ToolError("PAM DEPTH 必须 >= 1, 实际 %d" % depth)
    if not 1 <= maxval <= 65535:
        raise ToolError("PAM MAXVAL %d 超出允许范围 1-65535" % maxval)
    tupletype = fields.get("TUPLTYPE", "(未写明, 由 DEPTH 推断)")
    raster_off = find_raster_start(data, pos)
    unit = 2 if maxval > 255 else 1
    expected = width * height * depth * unit
    return width, height, maxval, depth, tupletype, raster_off, expected, comments


def parse(path):
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise ToolError("无法读取文件: %s" % exc)
    if len(data) < 2 or data[:1] != b"P" or data[1:2] not in b"1234567":
        raise ToolError("魔数不是 P1-P7 (文件开头为 %r)" % data[:2])
    magic = data[:2].decode("ascii")
    info = MAGIC_INFO[magic]
    comments = 0
    if magic == "P7":
        (width, height, maxval, depth, tupletype,
         raster_off, expected, comments) = parse_pam(data, 2, comments)
    else:
        (width, height, maxval, depth, tupletype,
         raster_off, expected, comments) = parse_plain(magic, info, data, 2, comments)

    warnings = []
    available = None
    if raster_off is not None:
        available = len(data) - raster_off
        if expected is not None and available < expected:
            warnings.append("光栅数据不足: 需要 %d 字节, 实际可用 %d 字节(文件可能被截断)"
                            % (expected, available))

    return {
        "file": path,
        "file_size": len(data),
        "magic": magic,
        "format_name": info[0],
        "width": width,
        "height": height,
        "maxval": maxval,
        "depth": depth,
        "tupletype": tupletype,
        "samples_per_pixel": info[3] if info[3] is not None else depth,
        "raster_offset": raster_off,
        "raster_expected_bytes": expected,
        "raster_available": available,
        "comments": comments,
        "warnings": warnings,
    }


def render_text(res):
    lines = []
    lines.append("文件        : %s (%d 字节)" % (res["file"], res["file_size"]))
    lines.append("魔数        : %s" % res["magic"])
    lines.append("格式        : %s" % res["format_name"])
    lines.append("宽 × 高     : %d × %d 像素" % (res["width"], res["height"]))
    if res["magic"] in ("P1", "P4"):
        lines.append("最大灰度值  : 1 (PBM 没有 maxval 字段, 固定为 1; 1=黑 0=白)")
    else:
        line = "最大灰度值  : %d" % res["maxval"]
        if res["maxval"] > 255:
            line += " (样本按 2 字节大端存储)"
        lines.append(line)
    if res["magic"] == "P7":
        lines.append("深度 DEPTH  : %d 样本/像素" % res["depth"])
        lines.append("元组类型    : %s" % res["tupletype"])
    elif res["samples_per_pixel"] == 3:
        lines.append("每像素样本数: 3 (RGB)")
    else:
        lines.append("每像素样本数: 1 (灰度/位图)")
    if res["magic"] == "P4":
        lines.append("位图存储    : 每行按位打包(高位 MSB 在前), 行补齐到整字节 = 每行 %d 字节"
                     % ((res["width"] + 7) // 8))
    if res["raster_offset"] is not None:
        if res["raster_expected_bytes"] is None:
            lines.append("光栅数据    : 自偏移 %d 起为 ASCII 文本, 共 %d 字节"
                         % (res["raster_offset"], res["raster_available"]))
        else:
            state = "完整" if res["raster_available"] >= res["raster_expected_bytes"] else "不足!"
            lines.append("光栅数据    : 起始偏移 %d, 预期 %d 字节, 实际可用 %d — %s"
                         % (res["raster_offset"], res["raster_expected_bytes"],
                            res["raster_available"], state))
    else:
        lines.append("光栅数据    : 自偏移 %d 起为 ASCII 文本" % res["raster_offset"])
    lines.append("头部注释    : %d 处" % res["comments"])
    lines.append("")
    if res["warnings"]:
        lines.append("警告 (%d 条):" % len(res["warnings"]))
        for w in res["warnings"]:
            lines.append("  - " + w)
    else:
        lines.append("警告: 无")
    return "\n".join(lines) + "\n"


def main(argv=None):
    setup_stdio()
    ap = argparse.ArgumentParser(
        description="解析 PBM/PGM/PPM/PAM(P1-P7) 头部: 魔数、宽高、最大灰度值, 支持注释")
    ap.add_argument("file", help="PNM 文件路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = ap.parse_args(argv)
    try:
        res = parse(args.file)
    except ToolError as exc:
        die(str(exc))
    if args.json:
        sys.stdout.write(json.dumps(res, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(render_text(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
