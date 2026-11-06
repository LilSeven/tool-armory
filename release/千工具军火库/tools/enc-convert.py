#!/usr/bin/env python3
"""编码转换器 - 在 GBK/GB18030/UTF-8/UTF-16 等编码间转换文本文件，可选换行符处理。

用途
    将输入文件按 --from 编码解码（--from auto 时先用启发式探测），
    再按 --to 编码写出；可同时统一换行符（--eol lf/crlf/cr）。
    二进制文件（解码失败）默认跳过，可用 --errors replace 强制转换。

只用 Python 标准库。含 --dry-run，安全可逆。

示例命令
    python -I enc-convert.py gbk.txt -o utf8.txt --from auto --to utf-8
    python -I enc-convert.py a.txt -o b.txt --to utf-16 --eol crlf
    python -I enc-convert.py *.txt --to utf-8 --in-place --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

KNOWN_ENCODINGS = [
    "ascii", "utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be",
    "gbk", "gb18030", "big5", "shift_jis", "latin-1", "cp1252",
]


def detect_encoding(data: bytes) -> str:
    """内嵌的轻量探测：BOM -> 严格解码 -> 兜底。"""
    for enc, bom in (("utf-32", b"\xff\xfe\x00\x00"), ("utf-8-sig", b"\xef\xbb\xbf"),
                     ("utf-16", b"\xff\xfe"), ("utf-16", b"\xfe\xff")):
        if data.startswith(bom):
            return enc
    if data and all(b < 0x80 for b in data[:4096]):
        return "ascii"
    for enc in ("utf-8", "gb18030", "latin-1"):
        try:
            data[:65536].decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def convert(data: bytes, src: str, dst: str, eol: str, errors: str):
    """返回 (新字节, 实际使用的源编码, 是否有不可解码字节)。"""
    if src == "auto":
        src = detect_encoding(data)
    if src == "ascii":
        src = "utf-8"  # 纯 ASCII 按 utf-8 处理避免输出无意义
    had_bad = False
    try:
        text = data.decode(src)
    except UnicodeDecodeError:
        if errors == "strict":
            raise
        had_bad = True
        text = data.decode(src, errors="replace")

    if eol == "lf":
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        out_nl = "\n"
    elif eol == "crlf":
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
        out_nl = "\r\n"
    elif eol == "cr":
        text = text.replace("\r\n", "\n").replace("\n", "\r")
        out_nl = "\r"
    else:  # keep：仅把混合换行归一到文件中的多数换行
        counts = {n: text.count(n) for n in ("\r\n", "\n", "\r") if text.count(n)}
        if counts and len(counts) > 1:
            keep = max(counts, key=counts.get)
            other = {"\r\n": "\n", "\n": "\r", "\r": "\n"}
            if keep == "\r\n":
                text = text.replace("\r\n", "\n").replace("\r", "\n")
                if counts.get("\r\n"):
                    text = text.replace("\n", "\r\n")
            elif keep == "\n":
                text = text.replace("\r\n", "\n").replace("\r", "\n")
            else:
                text = text.replace("\r\n", "\r").replace("\n", "\r")
            out_nl = keep
        else:
            out_nl = None
    return text.encode(dst), src, had_bad, out_nl


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="文本文件编码转换（GBK/GB18030/UTF-8/UTF-16 等）")
    ap.add_argument("inputs", nargs="+", help="输入文件（支持通配符由 shell 展开）")
    ap.add_argument("-o", "--output", help="输出文件（仅当 inputs 只有一个文件时可用）")
    ap.add_argument("--from", dest="src", default="auto",
                    help=f"源编码，auto=自动探测；可选: {', '.join(KNOWN_ENCODINGS)}")
    ap.add_argument("--to", dest="dst", default="utf-8", help="目标编码（默认 utf-8）")
    ap.add_argument("--eol", choices=["lf", "crlf", "cr", "keep", "none"], default="none",
                    help="换行符处理（none=不动）")
    ap.add_argument("--in-place", action="store_true", help="直接覆盖原文件")
    ap.add_argument("--dry-run", action="store_true", help="只显示将要做的转换，不写文件")
    ap.add_argument("--errors", choices=["strict", "replace"], default="strict",
                    help="解码失败时的处理")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    if args.output and len(args.inputs) > 1:
        ap.error("-o/--output 只能配合单个输入文件使用")
    if args.output and args.in_place:
        ap.error("--in-place 与 -o/--output 互斥")
    try:
        "".encode(args.dst)
    except LookupError:
        ap.error(f"未知的目标编码: {args.dst}")

    rc = 0
    for p in args.inputs:
        path = Path(p)
        if not path.is_file():
            print(f"[跳过] {path}: 不是文件或不存在")
            rc = 2
            continue
        try:
            data = path.read_bytes()
            out, src, had_bad, _ = convert(data, args.src, args.dst, args.eol, args.errors)
        except (OSError, UnicodeDecodeError) as e:
            print(f"[错误] {path}: {e}")
            rc = 2
            continue
        target = path if args.in_place else Path(args.output) if args.output else None
        if target is None:
            target = path.with_suffix(path.suffix + f".{args.dst.lower().replace('-', '')}")
        if args.dry_run:
            print(f"[dry-run] {path} ({src}) -> {target} ({args.dst}, eol={args.eol})")
            continue
        try:
            target.write_bytes(out)
        except OSError as e:
            print(f"[错误] 写入 {target}: {e}")
            rc = 2
            continue
        note = "  (含替换字符)" if had_bad else ""
        print(f"[完成] {path} ({src}) -> {target} ({args.dst}, eol={args.eol}){note}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
