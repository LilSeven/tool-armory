#!/usr/bin/env python3
"""分段交换重命名 (swap-segments-rename)

按分隔符切分文件名主干并交换或重排各段。
例如「歌手 - 歌名.mp3」用 --swap 1,2 互换为「歌名 - 歌手.mp3」；
用 --order 3,1,2 可任意重排；段数不足的文件自动跳过。

用法:
    python swap-segments-rename.py <目录> " - " --swap 1,2        # 预览
    python swap-segments-rename.py <目录> " - " --swap 1,2 --apply
    python swap-segments-rename.py <目录> "_" --order 3,1,2 --apply
    python swap-segments-rename.py <目录> " - " --keep 2 --apply  # 只保留前 2 段

选项:
    --apply            真正执行重命名（缺省只预览）
    --swap I,J         交换第 I 段和第 J 段（1 起算），如 1,2
    --order A,B,C,...  按给定次序重排所有段（1 起算，段数须一致）
    --keep N           只保留前 N 段（可与 swap/order 叠加，在重排之后应用）
    --join STR         重排后的连接符，缺省沿用原分隔符
    --ext JPG,MP3      只处理这些扩展名

段序号说明: 第 1 段是分隔符前最左边的部分，以此类推；扩展名不参与切分。

示例:
    python swap-segments-rename.py D:\\music " - " --swap 1,2 --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_indices(spec: str, what: str) -> list[int]:
    try:
        idx = [int(t) for t in spec.split(",")]
    except ValueError:
        raise SystemExit(f"错误：{what} 格式应为逗号分隔的整数，如 1,2")
    if any(i < 1 for i in idx):
        raise SystemExit(f"错误：{what} 的段序号从 1 开始")
    return idx


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="按分隔符切分文件名并交换/重排各段")
    ap.add_argument("folder", type=Path)
    ap.add_argument("sep", help="分隔符字符串（原样匹配，如 \" - \"）")
    ap.add_argument("--apply", action="store_true")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--swap", metavar="I,J", help="交换第 I、J 段")
    g.add_argument("--order", metavar="A,B,C", help="按给定次序重排各段")
    ap.add_argument("--keep", type=int, metavar="N", help="重排后只保留前 N 段")
    ap.add_argument("--join", default=None, help="重排后的连接符，缺省沿用原分隔符")
    ap.add_argument("--ext", default="")
    args = ap.parse_args(argv)
    # Windows GBK 控制台无法编码部分字符时用占位符代替，避免崩溃
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    if not args.swap and not args.order and not args.keep:
        ap.error("需要 --swap / --order / --keep 至少一个")

    folder = args.folder
    if not folder.is_dir():
        print(f"错误：目录不存在: {folder}", file=sys.stderr)
        return 2

    swap = parse_indices(args.swap, "--swap") if args.swap else None
    order = parse_indices(args.order, "--order") if args.order else None
    exts = {e.strip().lower().lstrip(".") for e in args.ext.split(",") if e.strip()} or None
    join = args.join if args.join is not None else args.sep

    files = [p for p in folder.iterdir() if p.is_file()]
    if exts:
        files = [p for p in files if p.suffix.lower().lstrip(".") in exts]

    changed = 0
    skipped = 0
    for p in files:
        segs = p.stem.split(args.sep)
        if len(segs) < 2:
            print(f"  跳过（无分隔符）: {p.name}")
            skipped += 1
            continue
        if swap:
            i, j = swap
            if len(segs) < max(i, j):
                print(f"  跳过（段数不足 {len(segs)}）: {p.name}")
                skipped += 1
                continue
            segs[i - 1], segs[j - 1] = segs[j - 1], segs[i - 1]
        elif order:
            if len(order) != len(segs):
                print(f"  跳过（--order 段数 {len(order)} != 实际 {len(segs)}）: {p.name}")
                skipped += 1
                continue
            segs = [segs[k - 1] for k in order]
        if args.keep and len(segs) > args.keep:
            segs = segs[:args.keep]
        new_name = join.join(segs) + p.suffix
        dst = p.with_name(new_name)
        if dst == p:
            print(f"  跳过（结果同名）: {p.name}")
            skipped += 1
            continue
        if dst.exists():
            print(f"  跳过（目标已存在 {dst.name}）: {p.name}")
            skipped += 1
            continue
        if args.apply:
            p.rename(dst)
            print(f"  {p.name} -> {dst.name}")
        else:
            print(f"  [预览] {p.name} -> {dst.name}")
        changed += 1

    print(f"{'完成' if args.apply else '预览'}: 改动 {changed}，跳过 {skipped}"
          f"{'' if args.apply else '（加 --apply 执行）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
