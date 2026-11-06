#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""火星文加料 —— 给文字叠加杂乱变音符，生成 cursed 风格文字（Zalgo Text）。

对输入文字的每个字符随机叠加 Unicode 组合附加符号（上方、下方、贯穿三个
方向），输出"被诅咒的"乱码风格文字。仅依赖 Python 标准库。

用法：
    python zalgo-text.py "你好，世界"
    python zalgo-text.py -i high "cursed text"
    echo "hello" | python zalgo-text.py
    python zalgo-text.py --seed 42 -i medium "稳定输出"
"""

from __future__ import annotations

import argparse
import random
import sys
import unicodedata

# 组合附加符号取材区间
_RANGES = (
    (0x0300, 0x036F),  # Combining Diacritical Marks
    (0x1AB0, 0x1AFF),  # Combining Diacritical Marks Extended
    (0x1DC0, 0x1DFF),  # Combining Diacritical Marks Supplement
    (0x20D0, 0x20F0),  # Combining Marks for Symbols
    (0xFE20, 0xFE2F),  # Combining Half Marks
)

# "贯穿文字"的覆盖类组合符号，单独归组
_MID = {0x0334, 0x0335, 0x0336, 0x0337, 0x0338, 0x0489,
        0x20D2, 0x20E5, 0x20E8,
        0xFE20, 0xFE21, 0xFE22, 0xFE23, 0xFE24, 0xFE25, 0xFE26}

# 各强度下每个字符叠加数量的 (下限, 上限)：上方 / 下方 / 贯穿
_INTENSITY = {
    "low":    ((0, 2), (0, 2), (0, 1)),
    "medium": ((1, 6), (1, 5), (0, 2)),
    "high":   ((3, 14), (3, 12), (1, 4)),
}


def _build_pools():
    """按 Unicode 类别与结合位置，把变音符分成 上 / 下 / 贯穿 三组。"""
    up, down, mid = [], [], []
    for lo, hi in _RANGES:
        for cp in range(lo, hi + 1):
            ch = chr(cp)
            if unicodedata.category(ch) != "Mn":  # 只要组合记号
                continue
            if cp in _MID:
                mid.append(ch)
            elif unicodedata.combining(ch) == 220:  # 结合位置在下方
                down.append(ch)
            else:
                up.append(ch)
    return up, down, mid


UP_POOL, DOWN_POOL, MID_POOL = _build_pools()


def zalgo(text: str, rng: random.Random, level: str = "medium") -> str:
    """给 text 的每个字符叠加变音符，返回 cursed 风格文字。"""
    (up_min, up_max), (dn_min, dn_max), (md_min, md_max) = _INTENSITY[level]
    out = []
    for ch in text:
        out.append(ch)
        if unicodedata.category(ch) == "Mn":
            continue  # 输入本身是组合符的不再叠加
        marks = (
            rng.choices(UP_POOL, k=rng.randint(up_min, up_max))
            + rng.choices(DOWN_POOL, k=rng.randint(dn_min, dn_max))
            + rng.choices(MID_POOL, k=rng.randint(md_min, md_max))
        )
        rng.shuffle(marks)
        out.extend(marks)
    return "".join(out)


def _read_input(args) -> str:
    if args.text:
        return " ".join(args.text)
    if sys.stdin is not None and not sys.stdin.isatty():
        data = sys.stdin.read()
        if data.strip():
            return data.strip("\n")
    return ""


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="zalgo-text", description="给文字叠加杂乱变音符，生成 cursed 风格文字")
    parser.add_argument("text", nargs="*", help="待加料的文字，省略则读标准输入")
    parser.add_argument("-i", "--intensity", choices=sorted(_INTENSITY),
                        default="medium", help="加料强度（默认 medium）")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子，便于复现")
    args = parser.parse_args(argv)

    text = _read_input(args)
    if not text:
        parser.print_usage(sys.stderr)
        sys.stderr.write("zalgo-text: 请给出文字参数，或用管道喂入文本。\n")
        return 2

    rng = random.Random(args.seed)
    print(zalgo(text, rng, args.intensity))
    return 0


if __name__ == "__main__":
    sys.exit(main())
