#!/usr/bin/env python3
"""GBK 与 UTF-8 互转（gbk-utf8-convert）：中文场景一站式转换，
GBK/GB2312/GB18030 与 UTF-8 互转，自动识别源编码。

用法:
    python gbk-utf8-convert.py <文件...> -t {utf-8|gbk|gb18030} [-o <输出目录>] [--in-place] [--bom] [--errors E]
示例:
    python gbk-utf8-convert.py a.txt -t utf-8
    python gbk-utf8-convert.py *.txt -t gbk --in-place

说明:
    源编码自动识别顺序：BOM（utf-8-sig/utf-16）→ UTF-8 严格解码
    → GBK 严格解码（兼容 GB2312）→ GB18030 严格解码。
    注意：极少数 GBK 文件恰好也是合法 UTF-8（比如只含 ASCII），此时按 UTF-8 处理。
    -t utf-8 时可用 --bom 额外写入 UTF-8 BOM；--bom 对 GBK 目标无意义，会报错。
    每个文件转换后打印识别到的源编码与去向。

退出码: 0 全部成功；1 有文件转换失败；2 用法错误。
"""

import argparse
import os
import sys

TARGETS = {"utf-8": "utf-8", "gbk": "gbk", "gb18030": "gb18030"}


def detect(data):
    """识别源编码，返回 (编解码器, 依据)；无法识别返回 (None, 原因)。"""
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", "检测到 UTF-8 BOM"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16", "检测到 UTF-16 BOM"
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    else:
        if all(b < 0x80 for b in data):
            return "ascii", "纯 ASCII（UTF-8 兼容）"
        return "utf-8", "严格 UTF-8 解码成功"
    try:
        data.decode("gbk")
        return "gbk", "GBK 严格解码成功（向下兼容 GB2312）"
    except UnicodeDecodeError:
        pass
    try:
        data.decode("gb18030")
        return "gb18030", "GB18030 严格解码成功"
    except UnicodeDecodeError:
        pass
    return None, "无法识别为 UTF-8 / GBK / GB18030"


def dest_path(src_path, dst, outdir, in_place):
    if in_place:
        return src_path
    d, base = os.path.split(src_path)
    stem, ext = os.path.splitext(base)
    if not ext:
        ext = ".txt"
    return os.path.join(outdir or d, "%s.%s%s" % (stem, dst, ext))


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(
        description="GBK/GB2312/GB18030 与 UTF-8 互转，自动识别源编码")
    ap.add_argument("files", nargs="+", help="输入文件（可多个）")
    ap.add_argument("-t", "--to", dest="dst", required=True,
                    choices=sorted(TARGETS), help="目标编码")
    ap.add_argument("-o", "--output", help="输出目录（默认与源文件同目录）")
    ap.add_argument("--in-place", action="store_true", help="就地覆盖原文件")
    ap.add_argument("--bom", action="store_true",
                    help="目标为 utf-8 时写入 BOM（即 utf-8-sig）")
    ap.add_argument("--errors", default="strict",
                    choices=["strict", "replace", "ignore"],
                    help="编码错误处理策略（默认 strict）")
    args = ap.parse_args(argv)

    if args.in_place and args.output:
        ap.error("--in-place 与 -o 不能同时使用")
    if args.bom and args.dst != "utf-8":
        ap.error("--bom 仅在 -t utf-8 时可用")
    dst_codec = "utf-8-sig" if (args.bom and args.dst == "utf-8") else args.dst
    if args.output:
        os.makedirs(args.output, exist_ok=True)

    failed = 0
    for path in args.files:
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as e:
            print("[失败] %s: 无法读取: %s" % (path, e), file=sys.stderr)
            failed += 1
            continue
        src, why = detect(data)
        if src is None:
            print("[失败] %s: %s" % (path, why), file=sys.stderr)
            failed += 1
            continue
        family = {"utf-8-sig": "utf-8", "ascii": "utf-8", "utf-16": "utf-16"}.get(src, src)
        if family == args.dst and not (args.bom and src == "utf-8"):
            print("[跳过] %s: 已是 %s（%s）" % (path, args.dst, why))
            continue
        try:
            text = data.decode(src, errors=args.errors)
            out = text.encode(dst_codec, errors=args.errors)
        except (UnicodeDecodeError, UnicodeEncodeError) as e:
            print("[失败] %s: 识别为 %s，但转换出错: %s（可尝试 --errors replace）"
                  % (path, src, e), file=sys.stderr)
            failed += 1
            continue
        dest = dest_path(path, args.dst, args.output, args.in_place)
        try:
            with open(dest, "wb") as f:
                f.write(out)
        except OSError as e:
            print("[失败] %s: 无法写出 %s: %s" % (path, dest, e), file=sys.stderr)
            failed += 1
            continue
        print("[完成] %s: %s -> %s（依据: %s；%d 字节 -> %d 字节） -> %s"
              % (path, src, dst_codec, why, len(data), len(out), dest))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
