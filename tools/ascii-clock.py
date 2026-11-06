#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ascii-clock 字符时钟 —— 点阵大数字显示当前时间，可切换秒表模式。

用途：
    用 3x5 点阵字体按倍率放大后显示 HH:MM:SS；默认时钟模式显示
    当前系统时间（循环刷新时冒号按半秒闪烁），加 --stopwatch 进入
    秒表模式，从 00:00.0 开始计时（精确到 0.1 秒）。Ctrl+C 退出；
    输出被重定向时逐帧打印，便于测试与录制。

示例命令：
    python ascii-clock.py --once               # 打印一帧当前时间后退出
    python ascii-clock.py                      # 时钟模式持续刷新
    python ascii-clock.py --stopwatch          # 秒表模式
    python ascii-clock.py --scale 3 --once     # 更大的点阵（自动适配终端宽度）
"""

import argparse
import os
import shutil
import sys
import time

FONT = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    ":": ("0", "0", "1", "0", "1"),
    ".": ("0", "0", "0", "0", "1"),
    " ": ("0", "0", "0", "0", "0"),
}
BLOCK = "\u2588"  # █


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="字符时钟：点阵大数字显示时间/秒表")
    parser.add_argument("--stopwatch", action="store_true",
                        help="秒表模式（默认为时钟模式）")
    parser.add_argument("--scale", type=int, default=2, help="点阵放大倍率 1-4（默认 2）")
    parser.add_argument("--delay", type=float, default=0.05, help="刷新间隔秒数（默认 0.05）")
    parser.add_argument("--frames", type=int, default=0, help="最大帧数，0=无限（默认 0）")
    parser.add_argument("--once", action="store_true", help="只打印一帧就退出")
    return parser.parse_args(argv)


def compose(text, scale):
    rows = [""] * (5 * scale)
    for ch in text:
        glyph = FONT[ch]
        for r in range(5 * scale):
            line = glyph[r // scale]
            seg = "".join((BLOCK if cell == "1" else " ") * scale for cell in line)
            rows[r] += seg + " " * scale
    return "\n".join(rows)


def stopwatch_text(elapsed):
    total_tenths = int(elapsed * 10)
    minutes, rem = divmod(total_tenths, 600)
    seconds, tenths = divmod(rem, 10)
    return "%02d:%02d.%d" % (minutes, seconds, tenths)


def main(argv=None):
    args = parse_args(argv)
    if os.name == "nt":
        os.system("")  # 让 Windows 控制台启用 ANSI 转义序列
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    cols, _rows = shutil.get_terminal_size(fallback=(80, 24))
    scale = min(4, max(1, args.scale))
    scale = max(1, min(scale, cols // 27))  # HH:MM:SS 放大后约 27*scale 列
    plain = not sys.stdout.isatty()
    start = time.monotonic()
    frames_total = 1 if args.once else args.frames
    frame = 0
    try:
        if not plain:
            sys.stdout.write("\x1b[2J")  # 清屏一次
        while frames_total <= 0 or frame < frames_total:
            if args.stopwatch:
                text = stopwatch_text(time.monotonic() - start)
                status = "stopwatch %s | Ctrl+C 退出" % text
            else:
                text = time.strftime("%H:%M:%S")
                if not args.once and int(time.time() * 2) % 2 == 0:
                    text = text.replace(":", " ")  # 冒号半秒闪烁
                status = "clock %s | Ctrl+C 退出" % time.strftime("%H:%M:%S")
            body = compose(text, scale)
            if plain:
                sys.stdout.write(body + "\n" + status + "\n\n")
            else:
                sys.stdout.write(("\x1b[2J" if frame == 0 else "") + "\x1b[H")
                sys.stdout.write(body + "\n" + status + "\n")
            sys.stdout.flush()
            frame += 1
            if args.once:
                break
            if args.delay > 0:
                time.sleep(args.delay)
    except KeyboardInterrupt:
        pass
    finally:
        if not plain:
            sys.stdout.write("\x1b[%d;1H" % (5 * scale + 3))
    return 0


if __name__ == "__main__":
    sys.exit(main())
