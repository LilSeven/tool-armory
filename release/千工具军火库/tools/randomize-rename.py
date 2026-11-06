#!/usr/bin/env python3
"""随机化重命名 (randomize-rename)

用随机字符串替换文件名主干（保留扩展名）做隐私脱敏，
并导出新旧名对照表 (CSV)，可用 --restore 配合对照表还原。

用法:
    python randomize-rename.py <目录>                    # 预览
    python randomize-rename.py <目录> --apply            # 执行并写 mapping.csv
    python randomize-rename.py <目录> --apply --len 12 --out map.csv
    python randomize-rename.py <目录> --restore map.csv  # 用对照表还原
    python randomize-rename.py <目录> --apply --prefix file_ --seed 42

选项:
    --apply            真正执行重命名（缺省只预览）
    --len N            随机串长度，缺省 10
    --prefix STR       随机名前缀，缺省空
    --charset STR      字符集，缺省小写字母+数字
    --seed N           固定随机种子（便于复现测试；正式脱敏勿用）
    --out PATH         对照表输出路径，缺省 <目录>/mapping.csv
    --restore PATH     按对照表反向还原（忽略 --apply，直接执行还原）
    --ext JPG,PNG      只处理这些扩展名

对照表为 UTF-8 CSV，两列: old,new（old 为原名）。还原时按 new->old 反查。

示例:
    python randomize-rename.py D:\\private --apply --out D:\\private\\map.csv
    python randomize-rename.py D:\\private --restore D:\\private\\map.csv
"""
from __future__ import annotations

import argparse
import csv
import secrets
import string
import sys
from pathlib import Path

DEFAULT_CHARSET = string.ascii_lowercase + string.digits


def rand_name(rng, length: int, prefix: str, charset: str, taken: set[str]) -> str:
    while True:
        body = "".join(rng.choice(charset) for _ in range(length))
        name = prefix + body
        if name not in taken:
            taken.add(name)
            return name


def do_restore(folder: Path, mapping_path: Path) -> int:
    if not mapping_path.is_file():
        print(f"错误：对照表不存在: {mapping_path}", file=sys.stderr)
        return 2
    pairs: list[tuple[str, str]] = []
    with mapping_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pairs.append((row["old"], row["new"]))
    changed = 0
    # 逆序还原，避免链式冲突
    for old, new in reversed(pairs):
        src = folder / new
        dst = folder / old
        if not src.is_file():
            print(f"  跳过（文件不存在）: {new}")
            continue
        if dst.exists():
            print(f"  跳过（目标已存在）: {old}")
            continue
        src.rename(dst)
        print(f"  {new} -> {old}")
        changed += 1
    print(f"还原完成: {changed} 个文件")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="随机化重命名并导出新旧名对照表")
    ap.add_argument("folder", type=Path)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--len", type=int, default=10)
    ap.add_argument("--prefix", default="")
    ap.add_argument("--charset", default=DEFAULT_CHARSET)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--restore", type=Path, default=None)
    ap.add_argument("--ext", default="")
    args = ap.parse_args(argv)
    # Windows GBK 控制台无法编码部分字符时用占位符代替，避免崩溃
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    if args.restore:
        return do_restore(args.folder, args.restore)

    folder = args.folder
    if not folder.is_dir():
        print(f"错误：目录不存在: {folder}", file=sys.stderr)
        return 2
    if args.len < 1:
        print("错误：--len 必须 >= 1", file=sys.stderr)
        return 2
    if not args.charset:
        print("错误：--charset 不能为空", file=sys.stderr)
        return 2

    import random
    rng = random.Random(args.seed) if args.seed is not None else secrets.SystemRandom()

    exts = {e.strip().lower().lstrip(".") for e in args.ext.split(",") if e.strip()} or None
    files = [p for p in folder.iterdir() if p.is_file()]
    if exts:
        files = [p for p in files if p.suffix.lower().lstrip(".") in exts]

    taken = {p.name for p in folder.iterdir()}
    plan: list[tuple[Path, Path]] = []
    for p in files:
        dst = p.with_name(rand_name(rng, args.len, args.prefix, args.charset, taken)
                          + p.suffix)
        plan.append((p, dst))

    mapping_path = args.out or folder / "mapping.csv"
    rows = [(src.name, dst.name) for src, dst in plan]

    changed = 0
    for src, dst in plan:
        if args.apply:
            src.rename(dst)
            print(f"  {src.name} -> {dst.name}")
        else:
            print(f"  [预览] {src.name} -> {dst.name}")
        changed += 1

    if args.apply and plan:
        with mapping_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["old", "new"])
            w.writerows(rows)
        print(f"对照表已写入: {mapping_path}")
    elif not args.apply:
        print(f"（预览模式不写对照表；实际执行将写入 {mapping_path}）")

    print(f"{'完成' if args.apply else '预览'}: {changed} 个文件"
          f"{'' if args.apply else '（加 --apply 执行）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
