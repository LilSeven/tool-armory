#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""爱心函数 —— 按心形隐函数 (x²+y²-1)³ - x²y³ < 0 打印 ASCII 爱心，可在中间嵌入祝福语。

示例命令:
    python ascii-heart.py                               # 实心爱心（默认 20 行高）
    python ascii-heart.py --mode curve --size 24        # 只描心形轮廓曲线
    python ascii-heart.py --mode dots --size 22         # 点阵（棋盘抖动）爱心
    python ascii-heart.py --size 26 --message "I Love U"
    python ascii-heart.py --fill "#" --message "七夕快乐"
"""

import argparse
import sys


def heart_inside(x, y):
    """心形隐函数: 返回 True 表示点 (x, y) 在心形内部。"""
    return (x * x + y * y - 1) ** 3 - x * x * y ** 3 < 0


def build(size, mode, fill):
    rows = max(8, size)
    cols = rows * 2
    x0, x1 = -1.45, 1.45
    y0, y1 = -1.25, 1.45
    dx = (x1 - x0) / (cols - 1)
    dy = (y1 - y0) / (rows - 1)

    def px(c):
        return x0 + c * dx

    def py(r):
        return y1 - r * dy

    mask = [[False] * cols for _ in range(rows)]
    edge = [[False] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            # 用该格四角采样: 有内有外 => 跨越边界曲线; 全内 => 内部
            flags = (heart_inside(px(c), py(r)),
                     heart_inside(px(c + 1), py(r)),
                     heart_inside(px(c), py(r + 1)),
                     heart_inside(px(c + 1), py(r + 1)))
            mask[r][c] = any(flags)
            edge[r][c] = any(flags) and not all(flags)

    grid = [[" "] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            if mode == "curve":
                if edge[r][c]:
                    grid[r][c] = fill
            elif mode == "dots":
                if mask[r][c] and (r + c) % 2 == 0:
                    grid[r][c] = fill
            else:  # solid
                if mask[r][c]:
                    grid[r][c] = fill
    return grid, mask, rows, cols


def interior_spans(mask, rows, cols):
    """每行内部格的左右跨度，空行记为 None。"""
    spans = []
    for r in range(rows):
        cols_in = [c for c in range(cols) if mask[r][c]]
        spans.append((min(cols_in), max(cols_in)) if cols_in else None)
    return spans


def wrap_text(text, width):
    """按宽度折行：优先按空格断词，超长单词硬切。"""
    if not text:
        return []
    lines, cur = [], ""
    for word in text.split(" "):
        while len(word) > width:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[:width])
            word = word[width:]
        cand = (cur + " " + word) if cur else word
        if len(cand) <= width:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def embed(grid, mask, rows, cols, message):
    """把祝福语逐行放进心形内部：从最宽的中部行向外找足够宽的位置。"""
    spans = interior_spans(mask, rows, cols)
    band = [r for r in range(rows // 4, 3 * rows // 4) if spans[r]]
    if not band:
        return
    widths = {r: spans[r][1] - spans[r][0] + 1 for r in band}
    lines = wrap_text(message, max(1, max(widths.values())))
    center = band[len(band) // 2]
    order = sorted(band, key=lambda r: (abs(r - center), r))
    used = set()
    for line in lines:
        row = next((r for r in order if r not in used and widths[r] >= len(line)), None)
        if row is None:
            continue
        used.add(row)
        lc, rc = spans[row]
        c0 = (lc + rc) // 2 - len(line) // 2
        for j, ch in enumerate(line):
            if 0 <= c0 + j < cols and mask[row][c0 + j]:
                grid[row][c0 + j] = ch


def main(argv=None):
    ap = argparse.ArgumentParser(description="打印 ASCII 爱心（心形隐函数），可嵌入祝福语")
    ap.add_argument("--mode", choices=("solid", "curve", "dots"), default="solid",
                    help="solid=实心(默认) curve=轮廓曲线 dots=点阵")
    ap.add_argument("--size", type=int, default=20,
                    help="爱心行数（默认 20，列数约为 2 倍）")
    ap.add_argument("--fill", default="@", help="填充字符（默认 @）")
    ap.add_argument("--message", default="", metavar="TEXT", help="嵌入爱心中间的祝福语")
    args = ap.parse_args(argv)
    if len(args.fill) != 1:
        ap.error("--fill 只能是单个字符")

    grid, mask, rows, cols = build(args.size, args.mode, args.fill)
    if args.message:
        embed(grid, mask, rows, cols, args.message)
    for row in grid:
        print("".join(row).rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
