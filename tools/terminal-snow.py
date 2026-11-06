#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""终端飘雪 —— 屏幕缓缓落雪的动画，可指定雪花密度与风速。

在终端里模拟雪花持续飘落：雪花随机生成、下落并随风横漂，
落到底部可堆积成雪地。Ctrl+C 随时退出。

用法:
    python terminal-snow.py                        # 默认参数飘雪
    python terminal-snow.py --density 0.12 --wind 2
    python terminal-snow.py --duration 5 --fps 15 --no-color --no-pile

选项:
    --density FLOAT  雪花密度 0~1（默认 0.08，越大雪越密）
    --wind INT       风速 -5~5（默认 1，正值向右吹，负值向左）
    --fps FLOAT      帧率（默认 12）
    --duration SEC   运行秒数；缺省一直下雪直到 Ctrl+C
    --no-color       关闭 ANSI 颜色
    --no-pile        雪落到底不堆积

示例命令:
    python -I terminal-snow.py --duration 1 --fps 20 --density 0.1 --wind 2

退出码: 0 正常或 Ctrl+C 中断；2 参数错误。
"""
import argparse
import os
import random
import shutil
import sys
import time

FLAKE_CHARS = ".:*+·"
FLAKE_COLORS = (188, 213, 231, 245, 250, 255)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="terminal-snow", description="终端飘雪动画：密度与风速可调")
    parser.add_argument("--density", type=float, default=0.08,
                        help="雪花密度 0~1（默认 0.08）")
    parser.add_argument("--wind", type=int, default=1,
                        help="风速 -5~5，正值向右（默认 1）")
    parser.add_argument("--fps", type=float, default=12.0, help="帧率（默认 12）")
    parser.add_argument("--duration", type=float, default=None,
                        help="运行秒数，缺省一直运行")
    parser.add_argument("--no-color", action="store_true", help="不使用 ANSI 颜色")
    parser.add_argument("--no-pile", action="store_true", help="雪落到底不堆积")
    args = parser.parse_args(argv)
    if not (0 < args.density <= 1):
        parser.error("--density 需在 (0, 1] 区间")
    if not (-5 <= args.wind <= 5):
        parser.error("--wind 需在 -5~5 之间")
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


class Snow:
    """维护雪花列表与底部积雪，每帧推进一步并渲染。"""

    def __init__(self, width, height, density, wind, use_color, pile_on, rng):
        self.w = width
        self.h = height            # 总行数（最后一行为雪地/地面）
        self.density = density
        self.wind = wind
        self.use_color = use_color
        self.pile_on = pile_on
        self.rng = rng
        self.flakes = []           # 每片 [x, y, ch, color]
        self.ground = [" "] * width
        for _ in range(int(width * (height - 1) * density * 0.5)):
            self.flakes.append(self._spawn(anywhere=True))

    def _spawn(self, anywhere=False):
        rng = self.rng
        x = rng.randrange(self.w)
        y = rng.randrange(self.h - 1) if anywhere else 0
        return [x, y, rng.choice(FLAKE_CHARS), rng.choice(FLAKE_COLORS)]

    def step(self):
        rng = self.rng
        w = self.w
        alive = []
        for x, y, ch, color in self.flakes:
            if rng.random() < 0.85:
                y += 1
            drift = self.wind if rng.random() < 0.8 else rng.randint(-1, 1)
            x = (x + drift) % w
            if y >= self.h - 1:
                if self.pile_on:
                    self.ground[x] = rng.choice("*+. ")
                continue  # 落地消失
            alive.append([x, y, ch, color])
        self.flakes = alive
        # 顶部按密度补充新雪
        expect = self.density * w * 0.5
        count = int(expect) + (1 if rng.random() < expect - int(expect) else 0)
        for _ in range(count):
            self.flakes.append(self._spawn())

    def render(self) -> str:
        grid = [[None] * self.w for _ in range(self.h)]
        if self.pile_on:
            grid[self.h - 1] = [(ch, None) for ch in self.ground]
        for x, y, ch, color in self.flakes:
            if 0 <= y < self.h - 1:
                grid[y][x] = (ch, color)
        lines = []
        for row in grid:
            buf = []
            for cell in row:
                if cell is None:
                    buf.append(" ")
                    continue
                ch, color = cell
                if self.use_color and color is not None:
                    buf.append("\x1b[38;5;%dm%s\x1b[0m" % (color, ch))
                else:
                    buf.append(ch)
            lines.append("".join(buf) + "\x1b[K")
        return "\x1b[H" + "\n".join(lines)


def main(argv=None) -> int:
    args = parse_args(argv)
    enable_ansi()
    reconfigure_stdio()
    size = shutil.get_terminal_size((80, 22))
    width = min(size.columns, 200)
    height = min(size.lines, 50)
    rng = random.Random()
    snow = Snow(width, height, args.density, args.wind,
                not args.no_color, not args.no_pile, rng)
    frame_time = 1.0 / args.fps
    deadline = time.monotonic() + args.duration if args.duration is not None else None
    out = sys.stdout
    out.write("\x1b[?25l\x1b[2J")
    try:
        while True:
            t0 = time.monotonic()
            snow.step()
            out.write(snow.render())
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
