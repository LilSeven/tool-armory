#!/usr/bin/env python3
"""分形圣诞树（fractal-tree）—— 递归打印分形树，可调层数并挂彩灯字符。

用途:
    用递归分支算法在终端画一棵分形树：每根树枝按固定比例
    递归分叉出两根更细的树枝，末梢变成叶子（*）。
    --levels 调整递归层数，--lights 在叶子上挂彩灯字符（o O @），
    --star 在树顶放一颗星，--seed 固定随机形状。
    仅用 Python 标准库，单文件即可运行。

示例命令:
    python -I fractal-tree.py --levels 8 --seed 7
    python -I fractal-tree.py --levels 10 --lights --star --seed 42
    python -I fractal-tree.py --levels 6

参数:
    --levels N  递归层数（3-13，默认 8）
    --lights    在叶子上随机挂彩灯字符
    --star      树顶画一颗星
    --seed N    随机种子（可复现，默认 0）
"""

import argparse
import math
import random
import sys

TRUNK_LEN = 7.0     # 主干步数
RATIO = 0.72        # 每层树枝长度比例
BASE_SPREAD = 0.42  # 分叉基础角度（弧度）
STAR_CHAR = "@"     # 树顶的星
LIGHT_CHARS = "oO"


def build_tree(levels, seed, lights, star):
    rng = random.Random(seed)
    height = int(TRUNK_LEN * (1 - RATIO ** (levels + 1)) / (1 - RATIO)) + 5
    width = int(TRUNK_LEN * 4.5)
    canvas = [[" "] * width for _ in range(height)]
    leaves = []

    def draw(x, y, angle, length, depth):
        dx = math.sin(angle)
        dy = -math.cos(angle)
        ex, ey = x, y
        for _ in range(max(1, int(round(length)))):
            ex += dx
            ey += dy
            cx = int(round(ex))
            cy = int(round(ey))
            if 0 <= cx < width and 0 <= cy < height:
                if depth <= 2:
                    canvas[cy][cx] = "*"
                    if depth == 0:
                        leaves.append((cx, cy))
                elif abs(dx) < 0.35:
                    canvas[cy][cx] = "|"
                else:
                    canvas[cy][cx] = "/" if dx > 0 else "\\"
        if depth == 0:
            return
        spread = BASE_SPREAD * (0.8 + 0.4 * rng.random())
        nxt = length * RATIO * (0.9 + 0.2 * rng.random())
        draw(ex, ey, angle + spread, nxt, depth - 1)
        draw(ex, ey, angle - spread, nxt, depth - 1)

    draw(width / 2.0, height - 2.0, 0.0, TRUNK_LEN, levels)

    if lights and leaves:
        k = min(len(leaves), max(1, len(leaves) * 3 // 10))
        for cx, cy in rng.sample(leaves, k):
            canvas[cy][cx] = rng.choice(LIGHT_CHARS)

    if star:
        for row in canvas:
            for ci, ch in enumerate(row):
                if ch != " ":
                    row[ci] = STAR_CHAR
                    break
            else:
                continue
            break

    rows = ["".join(r).rstrip() for r in canvas]
    while rows and not rows[0].strip():
        rows.pop(0)
    while rows and not rows[-1].strip():
        rows.pop()
    return rows


def build_parser():
    p = argparse.ArgumentParser(
        prog="fractal-tree", description="递归打印分形圣诞树（可调层数、挂彩灯）"
    )
    p.add_argument("--levels", type=int, default=8, help="递归层数 3-13，默认 8")
    p.add_argument("--lights", action="store_true", help="在叶子上挂彩灯字符")
    p.add_argument("--star", action="store_true", help="树顶画一颗星")
    p.add_argument("--seed", type=int, default=0, help="随机种子，可复现，默认 0")
    return p


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)

    if not (3 <= args.levels <= 13):
        print("错误: --levels 需在 3-13 之间", file=sys.stderr)
        return 2

    rows = build_tree(args.levels, args.seed, args.lights, args.star)
    print(f"# fractal tree levels={args.levels} seed={args.seed}"
          f" lights={args.lights} star={args.star}")
    print("\n".join(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
