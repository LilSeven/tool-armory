#!/usr/bin/env python3
"""newline-convert 换行符转换：在 LF、CRLF、CR 三种换行风格之间批量转换文本文件。

用法:
  python newline-convert.py <路径...> --to lf|crlf|cr [--ext .txt,.py] [--dry-run]

示例:
  python newline-convert.py ./src --to lf --ext .txt,.py
  python newline-convert.py a.txt b.txt --to crlf --dry-run

说明:
  - 参数是文件则直接处理；是目录则递归扫描（--ext 按扩展名过滤，逗号分隔）。
  - 以二进制方式读写，不改动任何编码；先归一化为 LF 再替换为目标风格，
    因此混合换行的文件也会被统一。
  - --dry-run 只统计与预览，不写盘。
"""

import argparse
import sys
from pathlib import Path


def convert_bytes(data: bytes, target: str):
    """把字节串中的换行统一为 target 风格，返回 (新字节, 统计)。"""
    crlf = data.count(b"\r\n")
    # 归一化：先把 CRLF 和裸 CR 都变成 LF
    normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    lf = normalized.count(b"\n")
    if target == "lf":
        out = normalized
    elif target == "crlf":
        out = normalized.replace(b"\n", b"\r\n")
    else:  # cr
        out = normalized.replace(b"\n", b"\r")
    stats = {"crlf": crlf, "lf": lf - crlf, "cr": data.count(b"\r") - crlf}
    return out, stats


def iter_files(paths, exts):
    for p in paths:
        path = Path(p)
        if path.is_file():
            yield path
        elif path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and (not exts or f.suffix.lower() in exts):
                    yield f
        else:
            print(f"跳过（不存在）: {path}", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description="批量转换文本文件的换行风格（LF/CRLF/CR）")
    ap.add_argument("paths", nargs="+", help="文件或目录（目录会递归）")
    ap.add_argument("--to", required=True, choices=["lf", "crlf", "cr"], dest="target",
                    help="目标换行风格")
    ap.add_argument("--ext", default="", help="只处理这些扩展名，逗号分隔（仅目录扫描时生效）")
    ap.add_argument("--dry-run", action="store_true", help="只预览不写盘")
    args = ap.parse_args(argv)

    exts = {e.strip().lower() if e.strip().startswith(".") else "." + e.strip().lower()
            for e in args.ext.split(",") if e.strip()}
    # 纯文本标志的启发式：含有 NUL 字节的文件视为二进制，跳过
    changed = skipped = 0
    for f in iter_files(args.paths, exts):
        try:
            data = f.read_bytes()
        except OSError as e:
            print(f"读取失败 {f}: {e}", file=sys.stderr)
            skipped += 1
            continue
        if b"\x00" in data:
            print(f"跳过（疑似二进制）: {f}")
            skipped += 1
            continue
        out, stats = convert_bytes(data, args.target)
        if out == data:
            print(f"无需转换: {f}  (CRLF={stats['crlf']} LF={stats['lf']} CR={stats['cr']})")
            continue
        print(f"转换 {args.target.upper():4s} {f}  原计数 CRLF={stats['crlf']} LF={stats['lf']} CR={stats['cr']}")
        if not args.dry_run:
            try:
                f.write_bytes(out)
            except OSError as e:
                print(f"写入失败 {f}: {e}", file=sys.stderr)
                skipped += 1
                continue
        changed += 1
    verb = "将转换" if args.dry_run else "已转换"
    print(f"完成：{verb} {changed} 个文件，跳过 {skipped} 个。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
