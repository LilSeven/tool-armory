#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DVD 待机球 —— 经典 DVD logo 弹跳动画的字符版，撞角有彩蛋提示。

一个字符画的 DVD logo 在边框场地内四弹跳，每碰壁换一种颜色；
恰好同时撞到两条边（角落）时闪出“撞角彩蛋”提示并计数。Ctrl+C 退出。

用法:
    python dvd-bounce.py                      # 按终端大小弹跳
    python dvd-bounce.py --logo-text PLAY --fps 20
    python dvd-bounce.py --width 40 --height 12 --duration 5

选项:
    --logo-text TEXT   logo 中的文字（默认 DVD）
    --fps FLOAT        帧率（默认 15）
    --duration SEC     运行秒数；缺省一直弹到 Ctrl+C
    --width COLS       覆盖场地宽度（默认取终端宽度）
    --height ROWS      覆盖场地高度（默认取终端行数，留一行给状态栏）
    --no-color         不换彩色

示例命令:
    python -I dvd-bounce.py --width 13 --height 6 --fps 60 --duration 1   # 小场地易撞角

退出码: 0 正常或 Ctrl+C 中断；1 场地放不下 logo；2 参数错误。
"""
import argparse
import os
import random
import shutil
import sys
import time
from types import SimpleNamespace

PALETTE = [196, 202, 208, 214, 220, 226, 190, 154, 118, 82, 46,
           51, 45, 39, 33, 27, 21, 93, 129, 165, 201, 213]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="dvd-bounce", description="DVD logo 字符弹跳动画，撞角有彩蛋")
    parser.add_argument("--logo-text", default="DVD", help="logo 中的文字（默认 DVD）")
    parser.add_argument("--fps", type=float, default=15.0, help="帧率（默认 15）")
    parser.add_argument("--duration", type=float, default=None,
                        help="运行秒数，缺省一直运行")
    parser.add_argument("--width", type=int, default=None, help="覆盖场地宽度")
    parser.add_argument("--height", type=int, default=None, help="覆盖场地高度")
    parser.add_argument("--no-color", action="store_true", help="不使用彩色")
    args = parser.parse_args(argv)
    if args.fps <= 0:
        parser.error("--fps 必须大于 0")
    if args.logo_text == "":
        parser.error("--logo-text 不能为空")
    return args


def enable_ansi() -> None:
    """在 Windows 控制台尽量启用 ANSI 转义序列（其他平台无操作）。"""
    if os.name == "nt":
        os.system("")
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass


def reconfigure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def make_logo(text: str):
    """生成三行字符画：.----. / | text | / '----'"""
    w = len(text) + 4
    return [
        "." + "-" * (w - 2) + ".",
        "| " + text + " |",
        "'" + "-" * (w - 2) + "'",
    ]


def step_bounce(st, x0, x1, y0, y1) -> None:
    """推进一步物理：撞壁反向、换色、计数；同帧双撞算撞角彩蛋。"""
    hit_x = hit_y = False
    if st.x + st.dx > x1 or st.x + st.dx < x0:
        st.dx = -st.dx
        hit_x = True
    if st.y + st.dy > y1 or st.y + st.dy < y0:
        st.dy = -st.dy
        hit_y = True
    st.x += st.dx
    st.y += st.dy
    if hit_x or hit_y:
        st.bounces += 1
        st.color_idx = (st.color_idx + 1) % len(PALETTE)
    if hit_x and hit_y:
        st.corners += 1
        st.egg_left = 10
    elif st.egg_left > 0:
        st.egg_left -= 1


def render_frame(st, width, height, logo, use_color) -> str:
    logo_w = len(logo[0])
    grid = [[" "] * width for _ in range(height)]
    for x in range(width):
        grid[0][x] = "-"
        grid[height - 1][x] = "-"
    for y in range(height):
        grid[y][0] = "|"
        grid[y][width - 1] = "|"
    grid[0][0] = grid[0][width - 1] = "+"
    grid[height - 1][0] = grid[height - 1][width - 1] = "+"
    for j, line in enumerate(logo):
        row = grid[st.y + j]
        for i, ch in enumerate(line):
            row[st.x + i] = ch
    color = PALETTE[st.color_idx]
    lines = []
    for j, row in enumerate(grid):
        text = "".join(row)
        if use_color and st.y <= j < st.y + len(logo):
            text = (text[:st.x] + "\x1b[38;5;%dm" % color
                    + text[st.x:st.x + logo_w] + "\x1b[0m" + text[st.x + logo_w:])
        lines.append(text + "\x1b[K")
    if st.egg_left > 0:
        status = "★ CORNER HIT! 撞角彩蛋 ★  corners=%d  bounces=%d" % (
            st.corners, st.bounces)
        if use_color:
            status = "\x1b[1;7;38;5;220m" + status + "\x1b[0m"
    else:
        status = "DVD 待机中...  bounces=%d  corners=%d  color=256#%d" % (
            st.bounces, st.corners, color)
    return "\x1b[H" + "\n".join(lines) + "\n" + status + "\x1b[K"


def main(argv=None) -> int:
    args = parse_args(argv)
    enable_ansi()
    reconfigure_stdio()
    logo = make_logo(args.logo_text)
    logo_w, logo_h = len(logo[0]), len(logo)
    size = shutil.get_terminal_size((80, 22))
    width = args.width if args.width is not None else min(size.columns, 160)
    height = args.height if args.height is not None else min(size.lines - 1, 40)
    if width - 2 < logo_w or height - 2 < logo_h:
        print("错误：场地 %dx%d 太小，放不下 %dx%d 的 logo"
              % (width, height, logo_w, logo_h), file=sys.stderr)
        return 1
    x0, x1 = 1, width - 1 - logo_w
    y0, y1 = 1, height - 1 - logo_h
    rng = random.Random()
    st = SimpleNamespace(x=rng.randint(x0, x1), y=rng.randint(y0, y1),
                         dx=1, dy=1, bounces=0, corners=0, egg_left=0, color_idx=0)
    frame_time = 1.0 / args.fps
    deadline = time.monotonic() + args.duration if args.duration is not None else None
    out = sys.stdout
    out.write("\x1b[?25l\x1b[2J")
    try:
        while True:
            t0 = time.monotonic()
            step_bounce(st, x0, x1, y0, y1)
            out.write(render_frame(st, width, height, logo, not args.no_color))
            out.flush()
            if deadline is not None and time.monotonic() >= deadline:
                break
            delay = frame_time - (time.monotonic() - t0)
            if delay > 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        pass
    except BrokenPipeError:
        pass
    finally:
        try:
            out.write("\x1b[?25h\x1b[0m\n")
            out.flush()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
