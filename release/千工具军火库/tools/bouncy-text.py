#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bouncy-text 弹跳屏保字 —— 让一行文字在终端里像 DVD 屏保一样来回弹跳。

用途：
    一行文字在终端窗口内沿对角线移动，碰到边界即反弹，无限循环，
    按 Ctrl+C 退出。输出到终端时用 ANSI 转义码原位刷新；输出被
    重定向或通过管道传输时自动退化为逐帧打印，便于测试与录制。

示例命令：
    python bouncy-text.py                          # 默认文字 ZCode!
    python bouncy-text.py --text "HELLO ZCODE"     # 自定义文字
    python bouncy-text.py --text Hi --speed 2      # 每帧走 2 格
    python bouncy-text.py --text Hi --frames 20    # 跑 20 帧后自动退出
    python bouncy-text.py --text Hi --width 60 --height 15
"""

import argparse
import os
import shutil
import sys
import time


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="弹跳屏保字：一行文字在终端里像 DVD 屏保一样来回弹跳")
    parser.add_argument("--text", default="ZCode!", help="弹跳的文字（默认 ZCode!）")
    parser.add_argument("--speed", type=int, default=1, help="每帧移动格数（默认 1）")
    parser.add_argument("--delay", type=float, default=0.05, help="帧间隔秒数（默认 0.05）")
    parser.add_argument("--frames", type=int, default=0, help="最大帧数，0=无限（默认 0）")
    parser.add_argument("--width", type=int, default=0, help="舞台宽度，0=自动取终端宽（默认 0）")
    parser.add_argument("--height", type=int, default=0, help="舞台高度，0=自动取终端高（默认 0）")
    return parser.parse_args(argv)


def stage_size(args):
    cols, rows = shutil.get_terminal_size(fallback=(80, 24))
    width = args.width or max(20, cols)
    height = args.height or max(6, rows - 1)  # 底部留一行放状态栏
    return width, height


def render_frame(text, width, height, x, y, frame_no):
    lines = [" " * width for _ in range(height)]
    seg = text[: max(0, width - x)]
    row = lines[y]
    lines[y] = row[:x] + seg + row[x + len(seg):]
    body = "\n".join(lines)
    status = "[frame %4d] %s" % (frame_no, text)
    return body + "\n" + status


def bounce(x, y, dx, dy, text_len, width, height):
    x += dx
    if x <= 0:
        x, dx = 0, abs(dx)
    elif x + text_len >= width:
        x, dx = max(0, width - text_len), -abs(dx)
    y += dy
    if y <= 0:
        y, dy = 0, abs(dy)
    elif y >= height - 1:
        y, dy = height - 1, -abs(dy)
    return x, y, dx, dy


def main(argv=None):
    args = parse_args(argv)
    if os.name == "nt":
        os.system("")  # 让 Windows 控制台启用 ANSI 转义序列
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    width, height = stage_size(args)
    text = args.text[:width] or "ZCode!"
    speed = max(1, args.speed)
    x, y, dx, dy = 0, 0, speed, speed
    plain = not sys.stdout.isatty()
    frame = 0
    try:
        if not plain:
            sys.stdout.write("\x1b[2J")  # 清屏一次
        while args.frames <= 0 or frame < args.frames:
            body = render_frame(text, width, height, x, y, frame)
            if plain:
                sys.stdout.write(body + "\n\n")
            else:
                sys.stdout.write("\x1b[H" + body + "\n")
            sys.stdout.flush()
            x, y, dx, dy = bounce(x, y, dx, dy, len(text), width, height)
            frame += 1
            if args.delay > 0:
                time.sleep(args.delay)
    except KeyboardInterrupt:
        pass
    finally:
        if not plain:
            sys.stdout.write("\x1b[%d;1H" % (height + 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
