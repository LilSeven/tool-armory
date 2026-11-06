#!/usr/bin/env python3
"""通用编码转换（convert-encoding）：在任意两种 Python 编解码器之间批量转换文本文件。

用法:
    python convert-encoding.py -f <源编码> -t <目标编码> <文件...> [-o <输出目录|输出文件>] [--in-place] [--errors E]
    python convert-encoding.py --list
示例:
    python convert-encoding.py -f gbk -t utf-8 a.txt b.txt -o out
    python convert-encoding.py -f utf-8 -t big5 a.txt --in-place
    python convert-encoding.py --list          # 列出常用编解码器

说明:
    以二进制方式读取，用源编码严格解码、目标编码编码后写出，换行符原样保留。
    输出文件名默认为 <主名>.<目标编码><扩展名>；-o 指定输出目录，
    或在只有一个输入文件时直接指定输出文件路径；--in-place 就地覆盖。

退出码: 0 全部成功；1 有文件转换失败；2 用法错误。
"""

import argparse
import codecs
import os
import sys

COMMON = [
    "utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be",
    "gbk", "gb2312", "gb18030", "big5", "big5hkscs",
    "shift_jis", "euc-jp", "euc-kr", "cp1252", "latin-1", "ascii",
]


def target_path(src_path, dst_codec, outdir, outfile):
    if outfile:
        return outfile
    d, base = os.path.split(src_path)
    stem, ext = os.path.splitext(base)
    if not ext:
        ext = ".txt"
    name = "%s.%s%s" % (stem, dst_codec, ext)
    return os.path.join(outdir or d, name)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(
        description="在任意两种 Python 编解码器之间批量转换文本文件")
    ap.add_argument("-f", "--from", dest="src", help="源编码（Python 编解码器名）")
    ap.add_argument("-t", "--to", dest="dst", help="目标编码（Python 编解码器名）")
    ap.add_argument("files", nargs="*", help="输入文件（可多个）")
    ap.add_argument("-o", "--output",
                    help="输出目录；单输入文件时也可以是输出文件路径")
    ap.add_argument("--in-place", action="store_true", help="就地覆盖原文件")
    ap.add_argument("--errors", default="strict",
                    choices=["strict", "replace", "ignore", "xmlcharrefreplace"],
                    help="编解码错误处理策略（默认 strict）")
    ap.add_argument("--list", action="store_true", help="列出常用编解码器后退出")
    args = ap.parse_args(argv)

    if args.list:
        print("常用编解码器:")
        for c in COMMON:
            try:
                codecs.lookup(c)
                print("  %-12s ok" % c)
            except LookupError:
                print("  %-12s 不可用" % c)
        print("完整列表见 Python 文档 codecs 章节，任何 codecs.lookup 可用的名字都可以用。")
        return 0

    if not args.src or not args.dst:
        ap.error("必须同时指定 -f/--from 与 -t/--to（或使用 --list）")
    if not args.files:
        ap.error("至少提供一个输入文件")
    for c in (args.src, args.dst):
        try:
            codecs.lookup(c)
        except LookupError:
            print("[错误] 未知的编解码器: %s" % c, file=sys.stderr)
            return 2
    if args.in_place and args.output:
        ap.error("--in-place 与 -o 不能同时使用")

    outfile = None
    outdir = None
    if args.output:
        if len(args.files) == 1 and not args.output.endswith(("/", "\\")) \
                and not os.path.isdir(args.output):
            outfile = args.output
            parent = os.path.dirname(outfile)
            if parent:
                os.makedirs(parent, exist_ok=True)
        else:
            outdir = args.output
            os.makedirs(outdir, exist_ok=True)

    failed = 0
    for path in args.files:
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as e:
            print("[失败] %s: 无法读取: %s" % (path, e), file=sys.stderr)
            failed += 1
            continue
        try:
            text = data.decode(args.src, errors=args.errors)
            out = text.encode(args.dst, errors=args.errors)
        except (UnicodeDecodeError, UnicodeEncodeError, LookupError) as e:
            print("[失败] %s: %s" % (path, e), file=sys.stderr)
            failed += 1
            continue
        dest = path if args.in_place else target_path(path, args.dst, outdir, outfile)
        try:
            with open(dest, "wb") as f:
                f.write(out)
        except OSError as e:
            print("[失败] %s: 无法写出 %s: %s" % (path, dest, e), file=sys.stderr)
            failed += 1
            continue
        print("[完成] %s (%s -> %s) -> %s (%d 字节 -> %d 字节)"
              % (path, args.src, args.dst, dest, len(data), len(out)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
