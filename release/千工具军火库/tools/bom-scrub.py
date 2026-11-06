#!/usr/bin/env python3
"""BOM 清理器 - 检测并移除（或添加）UTF-8/UTF-16/UTF-32 BOM，逐文件报告处理结果。

用途
    扫描文件开头的字节序标记（BOM）：
      - 缺省：只检测并报告每个文件的 BOM 类型；
      - --remove：剥掉 BOM（按检测到的 BOM 长度截断头部字节）；
      - --add-utf8 / --add-utf16le / --add-utf16be：给无 BOM 的文件加上指定 BOM。
    支持递归处理目录、dry-run 预览，跳过疑似二进制与空文件。

只用 Python 标准库。

示例命令
    python -I bom-scrub.py a.txt b.txt                 # 仅检测报告
    python -I bom-scrub.py src/ -r --remove --dry-run  # 预览删除 BOM
    python -I bom-scrub.py src/ -r --remove            # 实际删除
    python -I bom-scrub.py a.txt --add-utf8            # 添加 UTF-8 BOM
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BOMS = [
    ("UTF-32 LE", b"\xff\xfe\x00\x00"),
    ("UTF-32 BE", b"\x00\x00\xfe\xff"),
    ("UTF-8", b"\xef\xbb\xbf"),
    ("UTF-16 LE", b"\xff\xfe"),
    ("UTF-16 BE", b"\xfe\xff"),
]
ADD = {"utf8": b"\xef\xbb\xbf", "utf16le": b"\xff\xfe", "utf16be": b"\xfe\xff"}
ADD_NAME = {"utf8": "UTF-8", "utf16le": "UTF-16 LE", "utf16be": "UTF-16 BE"}


def detect_bom(data: bytes):
    for name, bom in BOMS:
        if data.startswith(bom):
            return name, len(bom)
    return None, 0


def iter_files(paths, recursive):
    for p in paths:
        path = Path(p)
        if path.is_file():
            yield path
        elif path.is_dir():
            it = path.rglob("*") if recursive else path.iterdir()
            for f in sorted(it):
                if f.is_file() and not f.is_symlink():
                    yield f


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="检测并移除/添加 UTF BOM，逐文件报告")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--remove", action="store_true", help="移除检测到的 BOM")
    g.add_argument("--add-utf8", action="store_true", help="添加 UTF-8 BOM")
    g.add_argument("--add-utf16le", action="store_true", help="添加 UTF-16 LE BOM")
    g.add_argument("--add-utf16be", action="store_true", help="添加 UTF-16 BE BOM")
    ap.add_argument("-r", "--recursive", action="store_true", help="递归处理目录")
    ap.add_argument("--dry-run", action="store_true", help="只显示将要做的修改，不写入")
    ap.add_argument("paths", nargs="+", help="文件或目录")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    mode = "detect"
    if args.remove:
        mode = "remove"
    elif args.add_utf8:
        mode = "utf8"
    elif args.add_utf16le:
        mode = "utf16le"
    elif args.add_utf16be:
        mode = "utf16be"

    rc = 0
    n = n_act = 0
    for path in iter_files(args.paths, args.recursive):
        n += 1
        try:
            data = path.read_bytes()
        except OSError as e:
            print(f"[错误] {path}: {e}")
            rc = 2
            continue
        name, blen = detect_bom(data)
        tag = name if name else ("无 BOM" if data else "空文件")

        if mode == "detect":
            print(f"[检测] {path}: {tag}")
            continue

        if mode == "remove":
            if not name:
                print(f"[不动] {path}: 无 BOM")
                continue
            new = data[blen:]
            desc = f"移除 {name} BOM ({blen} 字节)"
        else:
            if data.startswith(ADD[mode][:2]) or name is not None:
                print(f"[不动] {path}: 已有 BOM（{tag}）")
                continue
            if not data:
                print(f"[跳过] {path}: 空文件")
                continue
            if b"\x00" in data and mode == "utf8":
                print(f"[跳过] {path}: 疑似二进制（含 NUL），不加 UTF-8 BOM")
                continue
            new = ADD[mode] + data
            desc = f"添加 {ADD_NAME[mode]} BOM"

        if args.dry_run:
            print(f"[dry-run] {path}: {desc}")
            n_act += 1
            continue
        try:
            path.write_bytes(new)
        except OSError as e:
            print(f"[错误] 写入 {path}: {e}")
            rc = 2
            continue
        print(f"[处理] {path}: {desc}")
        n_act += 1

    action = {"detect": "检测", "remove": "移除 BOM"}.get(mode, "添加 BOM")
    print(f"共扫描 {n} 个文件，{action} {n_act} 个")
    return rc


if __name__ == "__main__":
    sys.exit(main())
