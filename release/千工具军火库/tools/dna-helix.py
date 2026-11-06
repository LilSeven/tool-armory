#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dna-helix DNA 螺旋 —— 旋转的双螺旋链字符动画。

用途：
    用字符画出两条沿正弦曲线互相缠绕的链：A 链用 '@'（前景）/ '.'（背景），
    B 链用 'o'（前景）/ "'"（背景），并按固定间隔在两链之间画出
    碱基对竖线 '|'；相位随时间推进形成旋转效果。Ctrl+C 退出；
    输出被重定向时逐帧打印，便于测试与录制。

示例命令：
    python dna-helix.py                          # 默认尺寸随终端
    python dna-helix.py --frames 40 --delay 0.03 # 跑 40 帧（自测/录制用）
    python dna-helix.py --width 80 --height 14 --cycles 2.5 --speed 0.4
"""

import argparse
import math
import os
import shutil
import sys
import time

RUNG_EVERY = 4  # 每隔多少列画一条碱基对


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="DNA 螺旋：旋转的双螺旋链字符动画")
    parser.add_argument("--width", type=int, default=0, help="画布宽度，0=自动（默认 0）")
    parser.add_argument("--height", type=int, default=0, help="画布高度，0=自动（默认 0）")
    parser.add_argument("--cycles", type=float, default=2.0,
                        help="整屏包含的螺旋周期数（默认 2.0）")
    parser.add_argument("--speed", type=float, default=0.3,
                        help="每帧相位推进弧度（默认 0.3）")
    parser.add_argument("--delay", type=float, default=0.05, help="帧间隔秒数（默认 0.05）")
    parser.add_argument("--frames", type=int, default=0, help="最大帧数，0=无限（默认 0）")
    return parser.parse_args(argv)


def canvas_size(args):
    cols, rows = shutil.get_terminal_size(fallback=(80, 24))
    return args.width or max(20, cols), args.height or max(7, rows - 1)


def render_frame(width, height, phase, cycles, frame_no):
    grid = [[" "] * width for _ in range(height)]
    mid = (height - 1) / 2.0
    amp = max(1.0, height / 2.0 - 1.0)
    span = max(1, width)
    for x in range(width):
        ph = phase + x * cycles * 2.0 * math.pi / span
        r1 = int(round(mid + amp * math.sin(ph)))
        r2 = int(round(mid - amp * math.sin(ph)))
        r1 = min(max(r1, 0), height - 1)
        r2 = min(max(r2, 0), height - 1)
        a_front = math.cos(ph) >= 0
        if x % RUNG_EVERY == 0 and r1 != r2:  # 碱基对竖线
            for r in range(min(r1, r2) + 1, max(r1, r2)):
                grid[r][x] = "|"
        if a_front:  # 先画背景链，再画前景链
            grid[r2][x] = "'"
            grid[r1][x] = "@"
        else:
            grid[r1][x] = "."
            grid[r2][x] = "o"
    return "\n".join("".join(row) for row in grid) + \
        "\n[frame %4d] phase=%.2f" % (frame_no, phase)


def main(argv=None):
    args = parse_args(argv)
    if os.name == "nt":
        os.system("")  # 让 Windows 控制台启用 ANSI 转义序列
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    width, height = canvas_size(args)
    cycles = max(0.5, args.cycles)
    speed = max(0.01, args.speed)
    phase = 0.0
    plain = not sys.stdout.isatty()
    frame = 0
    try:
        if not plain:
            sys.stdout.write("\x1b[2J")  # 清屏一次
        while args.frames <= 0 or frame < args.frames:
            body = render_frame(width, height, phase, cycles, frame)
            if plain:
                sys.stdout.write(body + "\n\n")
            else:
                sys.stdout.write("\x1b[H" + body + "\n")
            sys.stdout.flush()
            phase += speed
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
