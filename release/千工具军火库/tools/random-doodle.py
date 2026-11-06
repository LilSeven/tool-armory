#!/usr/bin/env python3
"""随机抽象画 (random-doodle) -- 基于种子生成随机几何字符画, 同种子可复现。

示例命令:
    python random-doodle.py --seed 42
    python random-doodle.py --seed 7 --width 48 --height 16 --style boxes --frame
    python random-doodle.py --seed sun --style circles

说明:
    * --seed 接受任意字符串; 相同种子 + 相同宽高/风格 => 输出逐字节一致 (可复现)。
    * --style 可选: any / lines / boxes / circles / triangles / dots, 默认 any。
    * 不给 --seed 时按当前时间取种子, 并把实际种子写到 stderr, 供事后复现。
    * 单文件, 只依赖 Python 标准库; 输出强制 UTF-8。
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time


def force_utf8() -> None:
    """Windows 管道/Git Bash 下 stdout 默认是 ANSI 代码页 (如 gbk), 统一改成 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def make_grid(w: int, h: int) -> list[list[str]]:
    return [[" "] * w for _ in range(h)]


def put(grid: list[list[str]], x: int, y: int, ch: str) -> None:
    """写入一个字符; 越界自动忽略 (画布裁剪)。"""
    if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
        grid[y][x] = ch


def draw_line(grid: list[list[str]], rng: random.Random) -> None:
    """Bresenham 直线。"""
    h, w = len(grid), len(grid[0])
    x1, y1 = rng.randrange(w), rng.randrange(h)
    x2, y2 = rng.randrange(w), rng.randrange(h)
    ch = rng.choice("*/\\-|")
    dx, dy = abs(x2 - x1), abs(y2 - y1)
    sx = 1 if x2 >= x1 else -1
    sy = 1 if y2 >= y1 else -1
    err = dx - dy
    x, y = x1, y1
    while True:
        put(grid, x, y, ch)
        if x == x2 and y == y2:
            return
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


def draw_rect(grid: list[list[str]], rng: random.Random) -> None:
    h, w = len(grid), len(grid[0])
    x1, y1 = rng.randrange(w), rng.randrange(h)
    x2 = min(w - 1, x1 + rng.randint(2, max(2, w // 2)))
    y2 = min(h - 1, y1 + rng.randint(1, max(1, h // 2)))
    ch = rng.choice("#%@")
    filled = rng.random() < 0.35
    for y in range(y1, y2 + 1):
        for x in range(x1, x2 + 1):
            if filled or y in (y1, y2) or x in (x1, x2):
                put(grid, x, y, ch)


def draw_circle(grid: list[list[str]], rng: random.Random) -> None:
    h, w = len(grid), len(grid[0])
    cx, cy = rng.randrange(w), rng.randrange(h)
    r = rng.randint(2, max(3, min(w, h) // 3))
    ch = rng.choice("oO()")
    steps = max(24, 8 * r)
    for i in range(steps):
        a = 2.0 * math.pi * i / steps
        # 终端字符高约为宽的 2 倍, y 方向半径取 r/2 让圆看起来更圆
        put(grid, round(cx + r * math.cos(a)), round(cy + (r / 2.0) * math.sin(a)), ch)


def draw_triangle(grid: list[list[str]], rng: random.Random) -> None:
    h, w = len(grid), len(grid[0])
    x, y = rng.randrange(w), rng.randrange(h)
    size = rng.randint(3, max(4, min(w, h) // 2))
    ch = rng.choice("^/\\A")
    for i in range(size):
        half = i // 2
        for xx in range(x - half, x + half + 1):
            if i == size - 1 or xx in (x - half, x + half):
                put(grid, xx, y + i, ch)


def draw_dots(grid: list[list[str]], rng: random.Random) -> None:
    h, w = len(grid), len(grid[0])
    for _ in range(rng.randint(8, 24)):
        put(grid, rng.randrange(w), rng.randrange(h), rng.choice(".,'`"))


DRAWERS = {
    "any": (draw_line, draw_rect, draw_circle, draw_triangle, draw_dots),
    "lines": (draw_line, draw_line, draw_line, draw_dots),
    "boxes": (draw_rect, draw_rect, draw_rect, draw_dots),
    "circles": (draw_circle, draw_circle, draw_circle, draw_dots),
    "triangles": (draw_triangle, draw_triangle, draw_triangle, draw_dots),
    "dots": (draw_dots, draw_dots, draw_line),
}


def render(w: int, h: int, seed: str, style: str, frame: bool) -> str:
    rng = random.Random(f"random-doodle/{w}x{h}/{style}/{seed}")
    grid = make_grid(w, h)
    for _ in range(rng.randint(6, 14)):
        rng.choice(DRAWERS[style])(grid, rng)
    lines = ["".join(row) for row in grid]
    if frame:
        border = "+" + "-" * w + "+"
        lines = [border] + ["|" + ln + "|" for ln in lines] + [border]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(
        prog="random-doodle.py",
        description="基于种子生成随机几何字符画 (同种子可复现)",
    )
    parser.add_argument("--seed", default=None, help="任意字符串种子; 省略则随机生成并写到 stderr")
    parser.add_argument("--width", type=int, default=40, help="画布宽, 4~240, 默认 40")
    parser.add_argument("--height", type=int, default=14, help="画布高, 4~120, 默认 14")
    parser.add_argument("--style", default="any", choices=sorted(DRAWERS), help="形状风格, 默认 any")
    parser.add_argument("--frame", action="store_true", help="给画加边框")
    args = parser.parse_args(argv)

    if not (4 <= args.width <= 240 and 4 <= args.height <= 120):
        parser.error("--width 须在 4~240 之间, --height 须在 4~120 之间")

    seed = args.seed
    if seed is None:
        seed = str(time.time_ns())
        print(f"[未指定 --seed, 本次使用种子: {seed}]", file=sys.stderr)

    print(render(args.width, args.height, seed, args.style, args.frame))
    return 0


if __name__ == "__main__":
    sys.exit(main())
