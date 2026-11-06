#!/usr/bin/env python3
"""时间戳重命名 (mtime-rename)

按文件修改时间 (mtime) 把文件重命名为「日期_时间」样式，如 20261101_153045.jpg。
默认按扩展名保持原样；同一秒内多个文件自动追加序号后缀 _1/_2 避免冲突。

用法:
    python mtime-rename.py <目录>              # 预览（dry-run）
    python mtime-rename.py <目录> --apply      # 实际执行重命名
    python mtime-rename.py <目录> --apply --ext jpg,png --pattern "%Y%m%d_%H%M%S"
    python mtime-rename.py <目录> --apply --utc --reserve   # 反转同秒并列顺序

选项:
    --apply            真正执行重命名（缺省只预览）
    --ext JPG,PNG      只处理这些扩展名（大小写不敏感，缺省全部文件）
    --pattern STR      strftime 格式，缺省 %%Y%%m%%d_%%H%%M%%S
    --utc              使用 UTC 时间而非本地时间
    --time mtime|ctime|atime   取哪种时间，缺省 mtime
    --reserve          同一秒内的多个文件按倒序编号（默认按名字正序）

示例:
    python mtime-rename.py D:\\photos --apply --ext jpg
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def collect(folder: Path, exts: set[str] | None) -> list[Path]:
    files = [p for p in folder.iterdir() if p.is_file()]
    if exts:
        files = [p for p in files if p.suffix.lower().lstrip(".") in exts]
    return files


def stamp(path: Path, mode: str, utc: bool, pattern: str) -> str:
    if mode == "mtime":
        ts = path.stat().st_mtime
    elif mode == "ctime":
        ts = path.stat().st_ctime
    else:
        ts = path.stat().st_atime
    dt = datetime.fromtimestamp(ts, tz=timezone.utc if utc else None)
    return dt.strftime(pattern)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="按修改时间把文件重命名为日期时间样式")
    ap.add_argument("folder", type=Path, help="目标目录")
    ap.add_argument("--apply", action="store_true", help="实际执行（缺省只预览）")
    ap.add_argument("--ext", default="", help="仅处理这些扩展名，逗号分隔")
    ap.add_argument("--pattern", default="%Y%m%d_%H%M%S", help="strftime 格式串")
    ap.add_argument("--utc", action="store_true", help="使用 UTC 时间")
    ap.add_argument("--time", choices=("mtime", "ctime", "atime"), default="mtime")
    ap.add_argument("--reserve", action="store_true", help="同秒并列按倒序编号")
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
    files = collect(folder, exts)
    if not files:
        print("没有可处理的文件。")
        return 0

    # 按时间戳分组，组内按名字排序（或倒序），同组追加 _N
    groups: dict[str, list[Path]] = {}
    for p in files:
        groups.setdefault(stamp(p, args.time, args.utc, args.pattern), []).append(p)

    plan: list[tuple[Path, Path]] = []
    for base, group in groups.items():
        group.sort(key=lambda p: p.name.lower(), reverse=args.reserve)
        for i, p in enumerate(group):
            suffix = f"_{i + 1}" if len(group) > 1 else ""
            new_name = f"{base}{suffix}{p.suffix}"
            plan.append((p, p.with_name(new_name)))

    # 处理目标名冲突：目标已被其他文件占用且不在本计划内则加随机尾巴
    occupied = {p.name for p in folder.iterdir()} - {p.name for p, _ in plan}
    final_plan: list[tuple[Path, Path]] = []
    for src, dst in plan:
        while dst.name in occupied:
            dst = dst.with_name(dst.stem + "x" + dst.suffix)
        occupied.add(dst.name)
        final_plan.append((src, dst))

    changed = 0
    todo = [(src, dst) for src, dst in final_plan if src != dst]
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
