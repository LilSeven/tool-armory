#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""conway-toy 生命游戏玩具 —— 随机或自定义初始图案的康威生命游戏演示。

用途：
    在环形（上下左右相连）棋盘上演示康威生命游戏 B3/S23 规则：
    存活细胞周围恰有 2 或 3 个存活邻居则继续存活，死细胞恰有 3 个
    存活邻居则复活，其余情况死亡或保持死亡。支持随机播种、内置
    图案与自定义图案文件。Ctrl+C 退出；输出被重定向时逐帧打印。

示例命令：
    python conway-toy.py --random --rows 15 --cols 40 --steps 50 --seed 1
    python conway-toy.py --pattern glider --steps 40
    python conway-toy.py --pattern pulsar --rows 20 --cols 40 --steps 10
    python conway-toy.py --file cells.txt --steps 100   # 自定义图案文件
    # cells.txt 示例（O 为活细胞，其余字符为死细胞）：
    #   .O.
    #   ..O
    #   OOO
"""

import argparse
import os
import random
import shutil
import sys
import time

BUILTIN = {
    "block": ["OO", "OO"],
    "blinker": ["OOO"],
    "toad": [".OOO", "OOO."],
    "beacon": ["OO..", "OO..", "..OO", "..OO"],
    "glider": [".O.", "..O", "OOO"],
    "r-pentomino": [".OO", "OO.", ".O."],
    "pulsar": [
        "..OOO...OOO..",
        ".............",
        "O....O.O....O",
        "O....O.O....O",
        "O....O.O....O",
        "..OOO...OOO..",
        ".............",
        "..OOO...OOO..",
        "O....O.O....O",
        "O....O.O....O",
        "O....O.O....O",
        ".............",
        "..OOO...OOO..",
    ],
}

ALIVE_CHARS = set("Oo#@*")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="生命游戏玩具：随机或自定义初始图案的康威生命游戏演示")
    parser.add_argument("--rows", type=int, default=16, help="棋盘行数（默认 16）")
    parser.add_argument("--cols", type=int, default=48, help="棋盘列数（默认 48）")
    parser.add_argument("--random", action="store_true", help="随机播种初始棋盘")
    parser.add_argument("--density", type=float, default=0.25,
                        help="随机播种时的活细胞密度（默认 0.25）")
    parser.add_argument("--seed", type=int, default=None, help="随机数种子（便于复现）")
    parser.add_argument("--pattern", default="glider",
                        help="内置图案名: %s（默认 glider）" % ", ".join(sorted(BUILTIN)))
    parser.add_argument("--file", default=None,
                        help="从文本文件读初始图案，O/o/#/@/* 为活细胞")
    parser.add_argument("--steps", type=int, default=0,
                        help="演化代数后退出，0=无限（默认 0）")
    parser.add_argument("--delay", type=float, default=0.08, help="帧间隔秒数（默认 0.08）")
    return parser.parse_args(argv)


def load_pattern_file(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = [ln.rstrip("\r\n") for ln in fh]
    except OSError as exc:
        raise SystemExit("conway-toy: 无法读取图案文件: %s" % exc)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        raise SystemExit("conway-toy: 图案文件为空: %s" % path)
    return lines


def build_grid(args, rng):
    rows, cols = max(3, args.rows), max(3, args.cols)
    grid = [[False] * cols for _ in range(rows)]
    if args.file:
        pattern = load_pattern_file(args.file)
    elif args.random:
        density = min(1.0, max(0.0, args.density))
        for r in range(rows):
            for c in range(cols):
                grid[r][c] = rng.random() < density
        return grid, rows, cols
    else:
        if args.pattern not in BUILTIN:
            raise SystemExit("conway-toy: 未知图案 %r，可选: %s"
                             % (args.pattern, ", ".join(sorted(BUILTIN))))
        pattern = BUILTIN[args.pattern]
    ph = len(pattern)
    pw = max(len(ln) for ln in pattern)
    if ph > rows or pw > cols:
        raise SystemExit("conway-toy: 图案尺寸 %dx%d 超过棋盘 %dx%d，请增大 --rows/--cols"
                         % (pw, ph, cols, rows))
    top = max(0, (rows - ph) // 2)
    left = max(0, (cols - pw) // 2)
    for r, line in enumerate(pattern):
        for c, ch in enumerate(line):
            if ch in ALIVE_CHARS:
                grid[top + r][left + c] = True
    return grid, rows, cols


def step(grid, rows, cols):
    nxt = [[False] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            n = 0
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    if grid[(r + dr) % rows][(c + dc) % cols]:
                        n += 1
            nxt[r][c] = n == 3 or (grid[r][c] and n == 2)
    return nxt


def render(grid, rows, cols, gen):
    pop = sum(1 for row in grid for cell in row if cell)
    lines = ["gen %3d pop %3d (%dx%d)" % (gen, pop, rows, cols)]
    lines.extend("".join("O" if cell else "." for cell in row) for row in grid)
    return "\n".join(lines)


def main(argv=None):
    args = parse_args(argv)
    if os.name == "nt":
        os.system("")  # 让 Windows 控制台启用 ANSI 转义序列
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if not args.file and not args.random:
        shutil.get_terminal_size(fallback=(80, 24))  # 保持与其它工具一致的大小探测习惯
    rng = random.Random(args.seed)
    grid, rows, cols = build_grid(args, rng)
    plain = not sys.stdout.isatty()
    gen = 0
    try:
        if not plain:
            sys.stdout.write("\x1b[2J")  # 清屏一次
        while True:
            body = render(grid, rows, cols, gen)
            if plain:
                sys.stdout.write(body + "\n\n")
            else:
                sys.stdout.write("\x1b[H" + body + "\n")
            sys.stdout.flush()
            if args.steps > 0 and gen >= args.steps:
                break
            grid = step(grid, rows, cols)
            gen += 1
            if args.delay > 0:
                time.sleep(args.delay)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
