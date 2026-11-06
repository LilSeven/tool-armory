#!/usr/bin/env python3
"""utf16-to-utf8 UTF-16 专项转换：检测 UTF-16 BOM 与字节序（含无 BOM 猜测），
统一转换为 UTF-8。

用法:
  python utf16-to-utf8.py <路径...> [-o 输出目录] [--inplace] [--bom] [--dry-run]

示例:
  python utf16-to-utf8.py ./utf16dir -o ./out          # 结果写到 out/，原名不变
  python utf16-to-utf8.py a.txt --inplace              # 原地覆盖为 UTF-8
  python utf16-to-utf8.py a.txt --bom --dry-run        # 预览，并输出带 BOM 的 UTF-8

说明:
  - 检测顺序：FF FE → UTF-16LE；FE FF → UTF-16BE；无 BOM 时按 NUL 字节位置
    猜测字节序（奇数位 NUL 多 → LE，偶数位 NUL 多 → BE），并给出猜测说明。
  - 非 UTF-16 文件（如已是 UTF-8/ASCII）跳过不动。
  - 默认写到 <输入名>.utf8.txt；-o 指定输出目录；--inplace 原地覆盖；
    --bom 输出带 BOM 的 UTF-8。
"""

import argparse
import sys
from pathlib import Path


def detect_utf16(data: bytes):
    """返回 (codec, bom 有无, 说明)；不是 UTF-16 返回 (None, ...)。"""
    if data.startswith(b"\xff\xfe") and not data.startswith(b"\xff\xfe\x00\x00"):
        return "utf-16-le", True, "BOM=FF FE，小端"
    if data.startswith(b"\xfe\xff"):
        return "utf-16-be", True, "BOM=FE FF，大端"
    if not data:
        return None, False, "空文件"
    # 无 BOM 猜测：UTF-16 的 ASCII 内容里 NUL 间隔出现
    nul_odd = sum(1 for i, b in enumerate(data) if b == 0 and i % 2 == 1)  # LE 中 NUL 在高字节位
    nul_even = sum(1 for i, b in enumerate(data) if b == 0 and i % 2 == 0)
    if nul_odd > nul_even and nul_odd >= 1:
        return "utf-16-le", False, f"无 BOM，按 NUL 位置猜测为小端（奇位 NUL={nul_odd}, 偶位={nul_even}）"
    if nul_even > nul_odd and nul_even >= 1:
        return "utf-16-be", False, f"无 BOM，按 NUL 位置猜测为大端（偶位 NUL={nul_even}, 奇位={nul_odd}）"
    return None, False, "未见 BOM，也无 UTF-16 特征（无成对 NUL），不是 UTF-16"


def iter_files(paths):
    for p in paths:
        path = Path(p)
        if path.is_file():
            yield path
        elif path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file():
                    yield f
        else:
            print(f"跳过（不存在）: {path}", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description="UTF-16（含无 BOM）→ UTF-8 批量转换")
    ap.add_argument("paths", nargs="+", help="文件或目录（目录会递归）")
    ap.add_argument("-o", "--outdir", default="", help="输出目录（默认与原文件同目录）")
    ap.add_argument("--inplace", action="store_true", help="原地覆盖原文件")
    ap.add_argument("--bom", action="store_true", help="输出带 BOM 的 UTF-8")
    ap.add_argument("--dry-run", action="store_true", help="只检测预览，不写盘")
    args = ap.parse_args(argv)

    outdir = Path(args.outdir) if args.outdir else None
    converted = skipped = failed = 0
    for f in iter_files(args.paths):
        data = f.read_bytes()
        codec, has_bom, note = detect_utf16(data)
        if codec is None:
            print(f"跳过 {f}: {note}")
            skipped += 1
            continue
        try:
            text = data.decode(codec)
            # BOM 本身会解码成 U+FEFF 字符，转换时剥掉
            if text.startswith("\ufeff"):
                text = text[1:]
        except UnicodeDecodeError as e:
            print(f"失败  {f}: 按 {codec} 解码出错（{e}），可能是猜测错误", file=sys.stderr)
            failed += 1
            continue
        payload = (b"\xef\xbb\xbf" if args.bom else b"") + text.encode("utf-8")
        if args.inplace:
            target = f
        elif outdir is not None:
            target = outdir / f.name
        else:
            target = f.with_name(f.stem + ".utf8.txt")
        print(f"转换 {f} -> {target}  [{note}]")
        if not args.dry_run:
            if outdir is not None and not args.inplace:
                outdir.mkdir(parents=True, exist_ok=True)
            try:
                target.write_bytes(payload)
            except OSError as e:
                print(f"写入失败 {target}: {e}", file=sys.stderr)
                failed += 1
                continue
        converted += 1
    print(f"完成：转换 {converted}，跳过 {skipped}，失败 {failed}。")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
