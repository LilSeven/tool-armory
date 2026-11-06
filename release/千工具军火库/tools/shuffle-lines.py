#!/usr/bin/env python3
"""行序洗牌（shuffle-lines）——把文件或 stdin 的各行随机打乱后输出。

用途：抽签排先后、出题打乱题库行序、随机回顾清单等。

示例命令：
  python shuffle-lines.py names.txt               # 打乱 names.txt 各行并输出
  python shuffle-lines.py names.txt -n 3          # 打乱后只输出前 3 行（随机抽 3 条）
  cat names.txt | python shuffle-lines.py         # 从 stdin 读取并打乱
  python shuffle-lines.py quiz.txt --seed 42      # 固定随机种子，结果可复现
  python shuffle-lines.py a.txt b.txt             # 多文件按顺序合并后统一打乱

输入：一个或多个文本文件（用 - 或缺省表示 stdin），自动识别 utf-8 / gbk。
输出：打乱后的各行，写到 stdout。
退出码：0 成功（含空输入）；2 找不到文件等参数错误。
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


def _read_text(src: str) -> str:
    """读入文本，依次尝试 utf-8 / gbk 解码；'-' 表示 stdin。"""
    data = sys.stdin.buffer.read() if src == "-" else Path(src).read_bytes()
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="shuffle-lines",
        description="把文件或 stdin 的各行随机打乱后输出（类似 shuf）。",
    )
    parser.add_argument("files", nargs="*", metavar="FILE",
                        help="输入文本文件，可多个；缺省或 '-' 表示 stdin")
    parser.add_argument("-n", "--head", type=int, metavar="N",
                        help="打乱后只输出前 N 行")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子（相同种子结果可复现）")
    args = parser.parse_args(argv)

    lines: list[str] = []
    for src in (args.files or ["-"]):
        if src != "-" and not Path(src).is_file():
            print(f"错误：找不到文件 {src}", file=sys.stderr)
            return 2
        lines.extend(_read_text(src).splitlines())

    if not lines:
        print("提示：输入为空，没有可打乱的行。", file=sys.stderr)
        return 0

    random.Random(args.seed).shuffle(lines)

    count = len(lines) if args.head is None else max(0, min(args.head, len(lines)))
    for line in lines[:count]:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
