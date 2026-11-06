#!/usr/bin/env python3
"""随机文件抽样（random-filename）——从目录里随机挑一个文件打印出来。

用途：随机翻牌回顾旧笔记、从素材库随机挑文档、抽查文件等。

示例命令：
  python random-filename.py D:/notes             # 从目录随机挑 1 个文件，打印文件名
  python random-filename.py . --ext .md,.txt     # 只在扩展名 .md / .txt 里抽
  python random-filename.py . -n 3               # 随机挑 3 个（不重复）
  python random-filename.py . -r                 # 递归包含子目录
  python random-filename.py . --full             # 打印完整路径而不是纯文件名
  python random-filename.py . --seed 42          # 固定种子，结果可复现

输出：抽中的文件（每行一个），写到 stdout。
退出码：0 成功；1 目录里没有符合条件的文件；2 参数错误（目录不存在等）。
仅依赖 Python 标准库。
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path


def _utf8_stdio() -> None:
    """Windows 控制台/管道下强制 UTF-8 输出，避免中文乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _norm_exts(raw: str) -> set[str]:
    """把 '.md,.txt' / 'md txt' 之类的写法归一成 {'.md', '.txt'}。"""
    out = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip().lower()
        if not part:
            continue
        out.add(part if part.startswith(".") else "." + part)
    return out


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="random-filename",
        description="从目录里随机挑文件打印，用于随机回顾旧笔记。",
    )
    parser.add_argument("directory", nargs="?", default=".",
                        help="目标目录（默认当前目录）")
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="抽取个数（默认 1，不重复）")
    parser.add_argument("--ext", default="", metavar="EXTS",
                        help="只考虑这些扩展名，逗号分隔，大小写不敏感，如 .md,.txt")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="递归包含子目录")
    parser.add_argument("--full", action="store_true",
                        help="打印完整路径而不是纯文件名")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子（相同种子结果可复现）")
    args = parser.parse_args(argv)

    root = Path(args.directory)
    if not root.is_dir():
        print(f"错误：{args.directory} 不是目录或不存在", file=sys.stderr)
        return 2
    if args.count < 1:
        print("错误：-n/--count 必须 ≥ 1", file=sys.stderr)
        return 2

    exts = _norm_exts(args.ext)
    it = root.rglob("*") if args.recursive else root.iterdir()
    files = [p for p in it if p.is_file()
             and (not exts or p.suffix.lower() in exts)]

    if not files:
        print(f"提示：{root} 里没有符合条件的文件。", file=sys.stderr)
        return 1

    random.Random(args.seed).shuffle(files)
    if args.count > len(files):
        print(f"提示：符合条件的文件只有 {len(files)} 个，全部输出。", file=sys.stderr)
    for p in files[: min(args.count, len(files))]:
        print(str(p if args.full else p.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
