#!/usr/bin/env python3
"""换行符转换 - 检测并统一文件换行符为 LF/CRLF/CR，可递归处理目录。

用途
    检测文件中的换行符类型（LF / CRLF / CR / 混合），并统一转换为目标格式。
    支持递归处理目录、按扩展名过滤、dry-run 预览。默认跳过疑似二进制文件
    （含 NUL 字节）。

只用 Python 标准库。

示例命令
    python -I eol-convert.py file.txt --to crlf
    python -I eol-convert.py src/ -r --to lf --ext .py --ext .md
    python -I eol-convert.py logs/ -r --detect        # 只检测不修改
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

EOL_BYTES = {"lf": b"\n", "crlf": b"\r\n", "cr": b"\r"}
NAMES = {"lf": "LF (\\n)", "crlf": "CRLF (\\r\\n)", "cr": "CR (\\r)"}


def detect_eol(data: bytes) -> str:
    """返回 'lf' / 'crlf' / 'cr' / 'mixed' / 'none'。"""
    counts = {"crlf": data.count(b"\r\n"), "lf": 0, "cr": 0}
    # 统计不含 \r 的 \n 与不含 \r\n 上下文的 \r
    lf = data.count(b"\n")
    counts["lf"] = lf - counts["crlf"]
    cr = data.count(b"\r")
    counts["cr"] = cr - counts["crlf"]
    present = [k for k, v in counts.items() if v > 0]
    if not present:
        return "none"
    if len(present) == 1:
        return present[0]
    return "mixed"


def to_target(data: bytes, target: str) -> bytes:
    """把任意换行统一为 target（lf/crlf/cr）。"""
    # 先全部归一到 \n，再展开为目标
    t = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if target == "lf":
        return t
    if target == "crlf":
        return t.replace(b"\n", b"\r\n")
    return t.replace(b"\n", b"\r")


def iter_files(paths, recursive, exts, follow_symlinks=False):
    seen = set()
    for p in paths:
        path = Path(p)
        if path.is_file():
            yield path
        elif path.is_dir():
            if recursive:
                it = path.rglob("*")
            else:
                it = path.iterdir()
            for f in sorted(it):
                if f.is_file() and not f.is_symlink():
                    real = f.resolve()
                    if real not in seen:
                        seen.add(real)
                        if exts and f.suffix.lower() not in exts:
                            continue
                        yield f


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="检测并统一文件换行符为 LF/CRLF/CR")
    ap.add_argument("paths", nargs="+", help="文件或目录（目录需 -r）")
    ap.add_argument("--to", choices=["lf", "crlf", "cr"], default=None,
                    help="目标换行符（缺省=只检测）")
    ap.add_argument("-r", "--recursive", action="store_true", help="递归处理目录")
    ap.add_argument("--ext", action="append", default=[], metavar="EXT",
                    help="只处理指定扩展名（如 --ext .py，可多次）")
    ap.add_argument("--detect", action="store_true", help="只检测报告，不修改（缺省 --to 时也是）")
    ap.add_argument("--dry-run", action="store_true", help="显示将要做的修改，但不写入")
    ap.add_argument("--include-mixed-only", action="store_true",
                    help="只转换当前为混合换行的文件")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    exts = {e.lower() if e.startswith(".") else "." + e.lower() for e in args.ext}
    write_mode = args.to is not None and not args.detect
    rc = 0
    n_files = n_changed = 0

    for path in iter_files(args.paths, args.recursive, exts):
        n_files += 1
        try:
            data = path.read_bytes()
        except OSError as e:
            print(f"[错误] {path}: {e}")
            rc = 2
            continue
        if b"\x00" in data:
            print(f"[跳过] {path}: 疑似二进制文件（含 NUL），当前换行: -")
            continue
        kind = detect_eol(data)
        if kind == "none":
            print(f"[跳过] {path}: 无换行符")
            continue
        if args.include_mixed_only and kind != "mixed":
            continue
        if not write_mode:
            print(f"[检测] {path}: {NAMES.get(kind, kind)}")
            continue
        if kind == args.to:
            print(f"[不动] {path}: 已是 {NAMES[args.to]}")
            continue
        new = to_target(data, args.to)
        if args.dry_run:
            print(f"[dry-run] {path}: {NAMES.get(kind, kind)} -> {NAMES[args.to]}")
            n_changed += 1
            continue
        try:
            path.write_bytes(new)
        except OSError as e:
            print(f"[错误] 写入 {path}: {e}")
            rc = 2
            continue
        print(f"[转换] {path}: {NAMES.get(kind, kind)} -> {NAMES[args.to]}")
        n_changed += 1

    print(f"共扫描 {n_files} 个文件" + (f"，转换 {n_changed} 个" if write_mode else "（仅检测）"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
