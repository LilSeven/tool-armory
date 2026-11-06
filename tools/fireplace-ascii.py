#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""壁炉氛围灯 —— 火焰摇曳明暗变化的终端壁炉动画。

用经典“火效”算法（底部热源 + 向上扩散衰减）在终端里渲染一炉
摇曳的火焰：热力映射为字符与红黄渐变色，底部有柴火与炉台线。
Ctrl+C 随时退出。

用法:
    python fireplace-ascii.py                     # 按终端大小烧全屏
    python fireplace-ascii.py --width 60 --height 14
    python fireplace-ascii.py --duration 10 --fps 20 --no-color

选项:
    --width COLS    覆盖宽度（默认取终端宽度）
    --height ROWS   覆盖高度（默认取终端行数，最后一行为炉台）
    --fps FLOAT     帧率（默认 15）
    --duration SEC  运行秒数；缺省一直烧到 Ctrl+C
    --no-color      关闭 ANSI 颜色

示例命令:
    python -I fireplace-ascii.py --duration 1 --fps 20 --width 60 --height 12

退出码: 0 正常或 Ctrl+C 中断；2 参数错误。
"""
import argparse
import os
import random
import shutil
import sys
import time

RAMP = " .:-=+*#%@"          # 热力 0..MAX_HEAT -> 字符
MAX_HEAT = 36
COLORS = [None, "52", "88", "124", "160", "196", "202", "208", "214", "226"]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="fireplace-ascii", description="壁炉氛围灯：终端火焰动画")
    parser.add_argument("--width", type=int, default=None, help="覆盖宽度（列数）")
    parser.add_argument("--height", type=int, default=None, help="覆盖高度（行数）")
    parser.add_argument("--fps", type=float, default=15.0, help="帧率（默认 15）")
    parser.add_argument("--duration", type=float, default=None,
                        help="运行秒数，缺省一直运行")
    parser.add_argument("--no-color", action="store_true", help="不使用 ANSI 颜色")
    args = parser.parse_args(argv)
    if args.fps <= 0:
        parser.error("--fps 必须大于 0")
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


class Fire:
    """热力场：底部热源随机刷新，热量向上扩散并衰减。"""

    def __init__(self, width, fire_rows, rng):
        self.w = width
        self.h = fire_rows
        self.rng = rng
        self.heat = [[0] * width for _ in range(fire_rows)]

    def step(self) -> None:
        rng = self.rng
        w = self.w
        # 自顶向下、读取下一行的旧值：热量每帧只向上爬一行，火焰逐行升腾摇曳
        for y in range(self.h - 1):
            below = self.heat[y + 1]
            row = self.heat[y]
            for x in range(w):
                v = (below[(x - 1) % w] + below[x] + below[(x + 1) % w]) // 3
                v -= rng.randint(0, 5)
                row[x] = v if v > 0 else 0
        # 底部热源：柴火处随机明暗
        bottom = self.heat[self.h - 1]
        for x in range(w):
            r = rng.random()
            if r < 0.45:
                bottom[x] = MAX_HEAT
            elif r < 0.90:
                bottom[x] = rng.randint(12, MAX_HEAT)
            else:
                bottom[x] = rng.randint(0, 8)

    def render(self, use_color: bool) -> str:
        ramp_last = len(RAMP) - 1
        lines = []
        for row in self.heat:
            buf = []
            last_color = None
            for v in row:
                idx = v * ramp_last // MAX_HEAT
                ch = RAMP[idx]
                if ch == " ":
                    if last_color is not None:
                        buf.append("\x1b[0m")
                        last_color = None
                    buf.append(" ")
                    continue
                color = COLORS[idx] if use_color else None
                if color != last_color:
                    if last_color is not None:
                        buf.append("\x1b[0m")
                    if color is not None:
                        buf.append("\x1b[38;5;%sm" % color)
                    last_color = color
                buf.append(ch)
            if last_color is not None:
                buf.append("\x1b[0m")
            lines.append("".join(buf) + "\x1b[K")
        return "\x1b[H" + "\n".join(lines)


def hearth_line(width: int) -> str:
    """底部炉台线：一条地线，中间摆两截柴火。"""
    base = ["_"] * width
    logs = "( ____ )  ( ____ )"
    if width >= len(logs) + 4:
        start = (width - len(logs)) // 2
        for i, ch in enumerate(logs):
            base[start + i] = ch
    return "".join(base)


def main(argv=None) -> int:
    args = parse_args(argv)
    enable_ansi()
    reconfigure_stdio()
    size = shutil.get_terminal_size((80, 22))
    width = args.width if args.width is not None else min(size.columns, 200)
    height = args.height if args.height is not None else min(size.lines, 50)
    fire_rows = height - 1           # 最后一行留给炉台
    if fire_rows < 3 or width < 8:
        print("错误：画面太小（需至少 8 列、4 行）", file=sys.stderr)
        return 2
    rng = random.Random()
    fire = Fire(width, fire_rows, rng)
    hearth = hearth_line(width)
    frame_time = 1.0 / args.fps
    deadline = time.monotonic() + args.duration if args.duration is not None else None
    out = sys.stdout
    out.write("\x1b[?25l\x1b[2J")
    try:
        while True:
            t0 = time.monotonic()
            fire.step()
            out.write(fire.render(not args.no_color) + "\n" + hearth + "\x1b[K")
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
