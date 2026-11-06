#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生日祝福卡 (birthday-card)。

用途:
    输入名字(可带 --age 年龄)在终端生成一张生日贺卡，并画一个
    生日蛋糕；蛋糕上的蜡烛数量随年龄增长(显示上限 24 根，超过
    会在卡片里注明"实在插不下")。

示例命令:
    python birthday-card.py 小明                     # 默认 0 岁，无蜡烛
    python birthday-card.py Alice --age 25           # 25 根蜡烛
    python birthday-card.py 老王 --age 60 --plain    # 纯文本输出(无 ANSI 颜色)

只依赖 Python 标准库。
"""
from __future__ import annotations

import argparse
import ctypes
import os
import sys
import unicodedata

CAKE_CANDLE_CAP = 24
RESET = "\x1b[0m"


def setup_stdio() -> None:
    """把标准流固定成 UTF-8，避免 Windows 本地编码(如 GBK)炸出 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def enable_windows_ansi() -> None:
    """在 Windows 传统控制台里打开 VT 转义序列支持(非交互或失败时静默跳过)。"""
    if os.name != "nt" or not sys.stdout.isatty():
        return
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def dw(text: str) -> int:
    """显示宽度: 全角/宽字符按 2 列计，其余按 1 列。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1 for ch in text)


def fit(text: str, width: int) -> str:
    """把 text 用空格补齐到显示宽度 width(居中)。"""
    pad = max(0, width - dw(text))
    left = pad // 2
    return " " * left + text + " " * (pad - left)


def paint(text: str, color: str, plain: bool) -> str:
    return text if plain else f"\x1b[{color}m{text}{RESET}"


def build_card(name: str, age: int) -> str:
    shown = min(age, CAKE_CANDLE_CAP)
    note = f"{age} 岁啦，蛋糕上插了 {shown} 根蜡烛"
    if age > CAKE_CANDLE_CAP:
        note += "(实在插不下，意思一下!)"
    inner = max(28, dw(name) + 14, dw(note) + 4)
    lines = [
        "┌" + "─" * inner + "┐",
        "│" + fit("🎂 生日祝福卡 🎂", inner) + "│",
        "│" + fit(f"—— 献给 {name} ——", inner) + "│",
        "│" + fit(note, inner) + "│",
        "│" + fit("愿你所有愿望都成真!", inner) + "│",
        "└" + "─" * inner + "┘",
    ]
    return "\n".join(lines)


def build_cake(shown: int) -> str:
    lines: list[str] = []
    if shown > 0:
        lines.append("    " + " ".join("^" for _ in range(shown)))
        lines.append("    " + " ".join("i" for _ in range(shown)))
    inner = max(14, shown * 2 + 1)
    lines.append("  ." + "─" * inner + ".")
    lines.append(" (" + fit("~ 生日蛋糕 ~", inner) + ")")
    lines.append(" (" + fit("HAPPY BIRTHDAY", inner) + ")")
    lines.append("  '" + "─" * inner + "'")
    return "\n".join(lines)


def main() -> int:
    setup_stdio()
    parser = argparse.ArgumentParser(
        prog="birthday-card",
        description="输入名字生成终端生日贺卡，蛋糕蜡烛数随年龄。",
    )
    parser.add_argument("name", help="寿星的名字")
    parser.add_argument("--age", type=int, default=0, help="年龄(决定蜡烛数量, 默认 0)")
    parser.add_argument("--plain", action="store_true", help="纯文本输出，不用 ANSI 颜色")
    args = parser.parse_args()
    if not args.name.strip():
        parser.error("名字不能为空")
    if args.age < 0:
        parser.error("--age 不能为负数")
    enable_windows_ansi()
    name = args.name.strip()
    shown = min(args.age, CAKE_CANDLE_CAP)
    lines = build_card(name, args.age).split("\n")
    if not args.plain:
        lines[1] = paint(lines[1], "95", False)  # 标题粉色
        lines[2] = paint(lines[2], "96", False)  # 献给行青色
    print("\n".join(lines))
    print()
    print(paint(build_cake(shown), "93", args.plain))
    print()
    print(paint("🎂 生日快乐! 🎂".center(44), "95", args.plain))
    return 0


if __name__ == "__main__":
    sys.exit(main())
