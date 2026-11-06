#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""迷宫印刷机 —— 随机生成可解迷宫并打印，--solve 可叠加显示解答路径。

算法：深度优先回溯生成完美迷宫（任意两格之间恰有一条路），
入口在左上角、出口在右下角；--solve 用 BFS 求最短路径并以 '*' 标出。
相同 --seed 总是生成相同迷宫。

示例命令:
    python maze-printer.py
    python maze-printer.py -W 31 -H 15 --seed 7
    python maze-printer.py -W 21 -H 9 --seed 42 --solve
"""

import argparse
import random
import sys
from collections import deque

# 每格四面墙的位标记
N, S, E, W = 1, 2, 4, 8
MOVES = ((-1, 0, N, S), (1, 0, S, N), (0, 1, E, W), (0, -1, W, E))


def generate(width, height, rng):
    """DFS 回溯挖墙，返回 height x width 的墙位掩码表。"""
    walls = [[N | S | E | W] * width for _ in range(height)]
    seen = [[False] * width for _ in range(height)]
    seen[0][0] = True
    stack = [(0, 0)]
    while stack:
        y, x = stack[-1]
        options = []
        for dy, dx, bit, back in MOVES:
            ny, nx = y + dy, x + dx
            if 0 <= ny < height and 0 <= nx < width and not seen[ny][nx]:
                options.append((ny, nx, bit, back))
        if options:
            ny, nx, bit, back = rng.choice(options)
            walls[y][x] &= ~bit
            walls[ny][nx] &= ~back
            seen[ny][nx] = True
            stack.append((ny, nx))
        else:
            stack.pop()
    return walls


def build_grid(walls):
    """把墙位掩码表渲染成 (2H+1) x (2W+1) 的字符画布，并打开入口/出口。"""
    height, width = len(walls), len(walls[0])
    grid = [["#"] * (2 * width + 1) for _ in range(2 * height + 1)]
    for y in range(height):
        for x in range(width):
            gy, gx = 2 * y + 1, 2 * x + 1
            grid[gy][gx] = " "
            if not walls[y][x] & S:
                grid[gy + 1][gx] = " "
            if not walls[y][x] & E:
                grid[gy][gx + 1] = " "
    grid[1][0] = " "                      # 左上入口
    grid[2 * height - 1][2 * width] = " "  # 右下出口
    return grid


def solve(walls):
    """BFS 求左上到右下的最短路，返回 [(y, x), ...]（格坐标），保证存在。"""
    height, width = len(walls), len(walls[0])
    start, goal = (0, 0), (height - 1, width - 1)
    prev = {start: None}
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        y, x = cur
        for dy, dx, bit, _ in MOVES:
            ny, nx = y + dy, x + dx
            nxt = (ny, nx)
            if (0 <= ny < height and 0 <= nx < width
                    and not walls[y][x] & bit and nxt not in prev):
                prev[nxt] = cur
                q.append(nxt)
    if goal not in prev:
        return []
    path, cur = [], goal
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    return path


def draw_path(grid, path):
    """把路径画到画布：格中心与相邻格之间的通道都标 '*'。"""
    for (y, x) in path:
        grid[2 * y + 1][2 * x + 1] = "*"
    for (y1, x1), (y2, x2) in zip(path, path[1:]):
        grid[2 * y1 + 1 + (y2 - y1)][2 * x1 + 1 + (x2 - x1)] = "*"


def main(argv=None):
    ap = argparse.ArgumentParser(description="随机生成可解的 ASCII 迷宫并打印")
    ap.add_argument("-W", "--width", type=int, default=21, help="迷宫宽度（格数，默认 21）")
    ap.add_argument("-H", "--height", type=int, default=9, help="迷宫高度（格数，默认 9）")
    ap.add_argument("--seed", type=int, default=None, help="随机种子（相同种子生成相同迷宫）")
    ap.add_argument("--solve", action="store_true", help="叠加显示从入口到出口的解答路径")
    args = ap.parse_args(argv)
    if args.width < 2 or args.height < 2:
        ap.error("迷宫尺寸至少为 2x2")

    rng = random.Random(args.seed)
    walls = generate(args.width, args.height, rng)
    grid = build_grid(walls)
    if args.solve:
        draw_path(grid, solve(walls))
    for row in grid:
        print("".join(row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
