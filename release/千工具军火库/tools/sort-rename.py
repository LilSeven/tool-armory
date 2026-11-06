#!/usr/bin/env python3
"""排序编号重命名 (sort-rename)

按名称/大小/修改时间对文件排序后统一编号重命名（如 001.jpg、002.jpg）。
支持倒序，以及用 --start 衔接现有编号序列（如目录里已有 001-003，可从 004 接着编）。
数字感知排序（natural sort）：a2 排在 a10 之前。

用法:
    python sort-rename.py <目录>                      # 预览
    python sort-rename.py <目录> --apply              # 执行
    python sort-rename.py <目录> --apply --by size --reverse
    python sort-rename.py <目录> --apply --start 4 --pad 3
    python sort-rename.py <目录> --apply --prefix img_ --ext jpg

选项:
    --apply            真正执行重命名（缺省只预览）
    --by name|size|time 排序依据，缺省 name（time 为修改时间）
    --reverse          倒序
    --start N          起始编号，缺省 1；衔接现有序列时设为下一个编号
    --pad N            编号补零位数，缺省 3
    --prefix STR       编号前的前缀，缺省空
    --suffix STR       编号后的后缀（在扩展名前），缺省空
    --ext JPG,PNG      只处理这些扩展名

示例:
    python sort-rename.py D:\\music --apply --by time --start 4 --pad 2
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

_NUM_RE = re.compile(r"(\d+)")


def natural_key(name: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in _NUM_RE.split(name)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="排序后统一编号重命名")
    ap.add_argument("folder", type=Path)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--by", choices=("name", "size", "time"), default="name")
    ap.add_argument("--reverse", action="store_true")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--pad", type=int, default=3)
    ap.add_argument("--prefix", default="")
    ap.add_argument("--suffix", default="")
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
    if not files:
        print("没有可处理的文件。")
        return 0

    if args.by == "size":
        files.sort(key=lambda p: p.stat().st_size)
    elif args.by == "time":
        files.sort(key=lambda p: p.stat().st_mtime)
    else:
        files.sort(key=lambda p: natural_key(p.name))
    if args.reverse:
        files.reverse()

    num = args.start
    plan: list[tuple[Path, Path]] = []
    for p in files:
        new_name = f"{args.prefix}{num:0{args.pad}d}{args.suffix}{p.suffix}"
        plan.append((p, p.with_name(new_name)))
        num += 1

    # 避免与目录中不在计划内的既有文件冲突
    occupied = {p.name for p in folder.iterdir()} - {src.name for src, _ in plan}
    fixed: list[tuple[Path, Path]] = []
    for src, dst in plan:
        while dst.name in occupied:
            dst = dst.with_name(dst.stem + "x" + dst.suffix)
        occupied.add(dst.name)
        fixed.append((src, dst))
    plan = fixed

    changed = 0
    todo = [(src, dst) for src, dst in plan if src != dst]
    if args.apply:
        # 两阶段重命名：先改成临时名，避免源名与目标名互相占用
        tmps: list[tuple[Path, Path, Path]] = []
        for src, dst in todo:
            tmp = src.with_name(f"__rnm_{os.getpid()}_{id(dst)}{src.suffix}")
            src.rename(tmp)
            tmps.append((tmp, src, dst))
        for tmp, src, dst in tmps:
            if dst.exists():
                tmp.rename(src)
                print(f"  错误: 目标已存在 {dst}", file=sys.stderr)
                return 1
            tmp.rename(dst)
            print(f"  {src.name} -> {dst.name}")
            changed += 1
    else:
        for src, dst in todo:
            print(f"  [预览] {src.name} -> {dst.name}")
            changed += 1

    print(f"{'完成' if args.apply else '预览'}: {changed} 个文件"
          f"{'' if args.apply else '（加 --apply 执行）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
