#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""故障艺术字 (glitch-text)。

用途:
    把输入文字随机插入乱码字符、翻转大小写并加上横向抖动，
    生成终端 glitch 故障艺术效果；多帧渲染时有闪动错位感。

示例命令:
    python glitch-text.py "SYSTEM ERROR"                  # 非交互 1 帧 / 交互终端 8 帧动画
    python glitch-text.py "WARNING" --frames 6            # 只渲染 6 帧
    python glitch-text.py "危 机 四 伏" --intensity 0.6   # 更强的故障感
    python glitch-text.py "GLITCH" --seed 42 --plain      # 固定随机种子、纯文本

只依赖 Python 标准库。
"""
from __future__ import annotations

import argparse
import ctypes
import os
import random
import sys
import time

GLITCH_CHARS = "▓▒░█▄▀■□¤§¦¬±Ø×÷≠∆ΩΞΨ#@%&*+=~^?/\\|<>"
PALETTE = ("91", "92", "93", "94", "95", "96", "97")
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


def glitch_word(text: str, intensity: float, rng: random.Random) -> str:
    out = []
    for ch in text:
        if ch.isspace():
            out.append(ch)
            continue
        roll = rng.random()
        if roll < intensity * 0.45:
            out.append(rng.choice(GLITCH_CHARS))          # 直接替换成乱码
        elif roll < intensity * 0.7 and ch.isascii() and ch.isalpha():
            out.append(ch.swapcase())                     # 大小写抖动
        elif roll < intensity:
            out.append(ch + rng.choice(GLITCH_CHARS))     # 原字后插入乱码
        else:
            out.append(ch)
    return "".join(out)


def render_frame(text: str, intensity: float, rng: random.Random, plain: bool) -> str:
    line = " " * rng.randrange(4) + glitch_word(text, intensity, rng)  # 横向抖动
    if plain:
        return line
    colored = f"\x1b[{rng.choice(PALETTE)}m{line}{RESET}"
    if rng.random() < 0.15:
        colored = f"\x1b[7m{colored}{RESET}"              # 偶尔反色闪一下
    return colored


def main() -> int:
    setup_stdio()
    parser = argparse.ArgumentParser(
        prog="glitch-text",
        description="文字随机插入乱码与抖动，形成终端 glitch 故障艺术效果。",
    )
    parser.add_argument("text", help="要故障化的文字")
    parser.add_argument("--intensity", type=float, default=0.35, help="故障强度 0~1(默认 0.35)")
    parser.add_argument("--frames", type=int, default=0,
                        help="渲染帧数; 0=自动(交互终端 8 帧动画，管道模式 1 帧)")
    parser.add_argument("--interval", type=float, default=0.12, help="每帧间隔秒数(默认 0.12)")
    parser.add_argument("--seed", type=int, default=None, help="固定随机种子(复现效果)")
    parser.add_argument("--plain", action="store_true", help="纯文本输出，不用 ANSI 颜色")
    args = parser.parse_args()
    if not args.text.strip():
        parser.error("文字不能为空")
    if not 0.0 <= args.intensity <= 1.0:
        parser.error("--intensity 需在 0~1 之间")
    if args.frames < 0:
        parser.error("--frames 不能为负数")
    enable_windows_ansi()
    rng = random.Random(args.seed)
    frames = args.frames or (8 if sys.stdout.isatty() else 1)
    try:
        for _ in range(frames):
            print(render_frame(args.text, args.intensity, rng, args.plain))
            sys.stdout.flush()
            if args.interval > 0:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n故障停止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
