#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""彩虹字刷屏 (rainbow-paint)。

用途:
    把输入文本按字符染上渐变彩虹色，并一行行向左滚动刷屏，
    形成终端跑马灯/刷屏效果。

示例命令:
    python rainbow-paint.py "Hello, Rainbow!"            # 交互终端下一直滚动刷屏
    python rainbow-paint.py "你好，彩虹" --frames 20      # 只刷 20 帧
    python rainbow-paint.py "GO GO GO" --interval 0.02   # 滚得更快
    python rainbow-paint.py "hello" --256                # 256 色兼容模式

说明:
    在管道/重定向(非交互)下默认只渲染 1 帧；交互终端下 --frames 0
    (默认)会一直滚动，按 Ctrl+C 退出。
只依赖 Python 标准库。
"""
from __future__ import annotations

import argparse
import colorsys
import ctypes
import os
import sys
import time

SEP = "  ·  "
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


def hsv_ansi(hue: float, mode: str) -> str:
    r, g, b = colorsys.hsv_to_rgb(hue % 1.0, 1.0, 1.0)
    if mode == "256":
        ri, gi, bi = (int(v * 5 + 0.5) for v in (r, g, b))
        return f"\x1b[38;5;{16 + 36 * ri + 6 * gi + bi}m"
    return f"\x1b[38;2;{int(r * 255 + 0.5)};{int(g * 255 + 0.5)};{int(b * 255 + 0.5)}m"


def rainbow_line(text: str, hue_shift: float, mode: str, plain: bool) -> str:
    if plain:
        return text
    total = max(1, len(text))
    parts = []
    for i, ch in enumerate(text):
        hue = (i / total + hue_shift) % 1.0
        parts.append(hsv_ansi(hue, mode) + ch + RESET)
    return "".join(parts)


def main() -> int:
    setup_stdio()
    parser = argparse.ArgumentParser(
        prog="rainbow-paint",
        description="把输入文本渲染成渐变彩虹色并横向滚动刷屏。",
    )
    parser.add_argument("text", nargs="?", default="Hello, Rainbow!",
                        help="要刷屏的文本(默认 \"Hello, Rainbow!\")")
    parser.add_argument("--frames", type=int, default=0,
                        help="渲染帧数; 0=自动(交互终端无限滚动，管道模式 1 帧)")
    parser.add_argument("--interval", type=float, default=0.05, help="每帧间隔秒数(默认 0.05)")
    parser.add_argument("--256", dest="mode_256", action="store_true", help="用 256 色模式(兼容老旧终端)")
    parser.add_argument("--plain", action="store_true", help="纯文本输出，不上色")
    args = parser.parse_args()
    if not args.text.strip():
        parser.error("文本不能为空")
    if args.frames < 0:
        parser.error("--frames 不能为负数")
    enable_windows_ansi()
    mode = "256" if args.mode_256 else "truecolor"
    frames: int | None = args.frames
    if frames == 0:
        frames = None if sys.stdout.isatty() else 1
    text = args.text
    n = len(text)
    frame = 0
    try:
        while frames is None or frame < frames:
            off = frame % n
            line = text[off:] + SEP + text[:off]
            print(rainbow_line(line, (frame * 0.02) % 1.0, mode, args.plain))
            sys.stdout.flush()
            if args.interval > 0:
                time.sleep(args.interval)
            frame += 1
    except KeyboardInterrupt:
        print("\n刷屏结束，再见!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
