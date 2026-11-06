#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""倒计时礼炮 (countdown-celebrate)。

用途:
    在终端从指定秒数一路倒数到 0，随后撒出一场由随机彩色字符
    组成的彩带雨，做成一场终端小礼花。适合发布、庆功、跨年等
    需要一点仪式感的时刻。

示例命令:
    python countdown-celebrate.py                    # 默认从 3 倒数后放礼花
    python countdown-celebrate.py -n 10              # 从 10 秒开始倒数
    python countdown-celebrate.py -n 5 --fast        # 跳过全部延时直接放完
    python countdown-celebrate.py -n 3 --rain-frames 4 --plain   # 纯文本少量彩带

只依赖 Python 标准库; Windows 10+ / mintty / 主流 *nix 终端均可运行。
"""
from __future__ import annotations

import argparse
import ctypes
import math
import os
import random
import shutil
import sys
import time

CONFETTI = "✦✧·●○◆◇■□▲△♥♦★*+"
COLORS = ("31", "32", "33", "34", "35", "36", "91", "92", "93", "94", "95", "96", "97")
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


def paint(text: str, color: str, plain: bool) -> str:
    return text if plain else f"\x1b[{color}m{text}{RESET}"


def countdown(seconds: int, fast: bool, plain: bool) -> None:
    bar_w = max(10, min(30, seconds * 2))
    for i in range(seconds, 0, -1):
        filled = round(bar_w * i / seconds)
        bar = "█" * filled + "░" * (bar_w - filled)
        color = "31" if i * 3 > seconds * 2 else ("33" if i * 3 > seconds else "32")
        print(paint(f"倒计时 [ {bar} ] {i}".center(60), color, plain))
        if not fast:
            time.sleep(1)
    print(paint("0 —— 发射! 🎆".center(60), "95", plain))


def confetti_rain(fast: bool, plain: bool, frames: int = 14) -> None:
    cols = min(shutil.get_terminal_size((80, 24)).columns, 80)
    rows = 9
    rng = random.Random()
    particles: list[list] = []

    def spawn(n: int) -> None:
        for _ in range(n):
            particles.append([
                rng.randrange(cols),                # x 坐标
                float(rng.randrange(-rows, 0)),     # y 坐标(负数=还在画面外)
                rng.choice(CONFETTI),               # 彩带字符
                rng.choice(COLORS),                 # 颜色
                rng.choice((0.5, 1.0, 1.0, 1.5)),   # 下落速度
            ])

    spawn(cols // 2)
    for _ in range(max(1, frames)):
        grid: list[list[tuple[str, str]]] = [[(" ", "")] * cols for _ in range(rows)]
        for p in particles:
            p[1] += p[4]
            y = int(math.floor(p[1]))
            if y >= rows:  # 落地后回到顶部，换个花样继续撒
                p[0] = rng.randrange(cols)
                p[1] = 0.0
                p[2] = rng.choice(CONFETTI)
                p[3] = rng.choice(COLORS)
                y = 0
            if 0 <= y < rows and grid[y][p[0]][0] == " ":
                grid[y][p[0]] = (p[2], p[3])
        for row in grid:
            print("".join(ch if plain or not c else f"\x1b[{c}m{ch}{RESET}" for ch, c in row))
        if not fast:
            time.sleep(0.12)
    print(paint("✦ 礼炮放完，撒花完毕，干杯! ✦".center(60), "93", plain))


def main() -> int:
    setup_stdio()
    parser = argparse.ArgumentParser(
        prog="countdown-celebrate",
        description="倒数到零后撒彩带字符，放一场终端礼花。",
    )
    parser.add_argument("-n", "--seconds", type=int, default=3, help="倒计时秒数(默认 3)")
    parser.add_argument("--rain-frames", type=int, default=14, help="彩带雨帧数(默认 14)")
    parser.add_argument("--fast", action="store_true", help="不做任何延时，直接跑完动画")
    parser.add_argument("--plain", action="store_true", help="纯文本输出，不用 ANSI 颜色")
    args = parser.parse_args()
    if args.seconds < 0:
        parser.error("-n/--seconds 不能为负数")
    if args.rain_frames < 0:
        parser.error("--rain-frames 不能为负数")
    enable_windows_ansi()
    countdown(args.seconds, args.fast, args.plain)
    confetti_rain(args.fast, args.plain, args.rain_frames)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已取消。")
        sys.exit(130)
