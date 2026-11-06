#!/usr/bin/env python3
"""Unicode 规范化重命名 (unicode-rename)

对文件名做 Unicode 规范化（NFC/NFD），或剥离变音符转写为 ASCII 安全名。
例如 NFC 把「cafe\u0301」合成「café」；--ascii 把「café」转为「cafe」、
「北京.txt」可配合 --fallback 用占位符处理无 ASCII 对应的字符。

用法:
    python unicode-rename.py <目录> --mode nfc        # 预览
    python unicode-rename.py <目录> --mode nfc --apply
    python unicode-rename.py <目录> --mode ascii --apply
    python unicode-rename.py <目录> --mode ascii --apply --fallback _

选项:
    --apply            真正执行重命名（缺省只预览）
    --mode nfc|nfd|ascii
                       nfc/nfd: Unicode 规范化; ascii: NFKD 剥离变音符后
                       删除非 ASCII 字符
    --fallback STR     ascii 模式下非 ASCII 字符的替代串，缺省为直接删除；
                       若为空串且整名删空则跳过该文件
    --ext JPG,PNG      只处理这些扩展名

示例:
    python unicode-rename.py D:\\downloads --mode ascii --apply --fallback _
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

_MODES = {"nfc": "NFC", "nfd": "NFD", "ascii": "NFKD"}


def to_ascii(name: str, fallback: str) -> str:
    out = unicodedata.normalize("NFKD", name)
    out = "".join(c for c in out if not unicodedata.combining(c))
    out = out.encode("ascii", "ignore").decode("ascii")
    if fallback:
        # 先 NFKD 化原名，把仍非 ASCII 的位置替换为 fallback
        nfkd = unicodedata.normalize("NFKD", name)
        chars: list[str] = []
        for c in nfkd:
            if not unicodedata.combining(c):
                chars.append(c if c.isascii() else fallback)
        out = "".join(chars)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="对文件名做 NFC/NFD 规范化或转 ASCII")
    ap.add_argument("folder", type=Path)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--mode", choices=("nfc", "nfd", "ascii"), required=True)
    ap.add_argument("--fallback", default="", help="ascii 模式下非 ASCII 字符替代串")
    ap.add_argument("--ext", default="")
    args = ap.parse_args(argv)
    # Windows GBK 控制台无法编码部分字符时用占位符代替，避免崩溃
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    folder = args.folder
    if not folder.is_dir():
        print(f"错误：目录不存在: {folder}", file=sys.stderr)
        return 2

    exts = {e.strip().lower().lstrip(".") for e in args.ext.split(",") if e.strip()} or None
    files = [p for p in folder.iterdir() if p.is_file()]
    if exts:
        files = [p for p in files if p.suffix.lower().lstrip(".") in exts]

    changed = 0
    skipped = 0
    for p in files:
        if args.mode == "ascii":
            new_name = to_ascii(p.name, args.fallback)
            if not new_name or new_name == "." * len(new_name):
                print(f"  跳过（转 ASCII 后为空）: {p.name!r}")
                skipped += 1
                continue
        else:
            new_name = unicodedata.normalize(_MODES[args.mode], p.name)
        if new_name == p.name:
            continue
        dst = p.with_name(new_name)
        if dst.exists():
            print(f"  跳过（目标已存在 {new_name!r}）: {p.name!r}")
            skipped += 1
            continue
        if args.apply:
            p.rename(dst)
            print(f"  {p.name!r} -> {dst.name!r}")
        else:
            print(f"  [预览] {p.name!r} -> {dst.name!r}")
        changed += 1

    print(f"{'完成' if args.apply else '预览'}: 改动 {changed}，无需改动/跳过 {skipped}"
          f"{'' if args.apply else '（加 --apply 执行）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
