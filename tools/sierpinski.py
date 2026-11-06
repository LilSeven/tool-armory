#!/usr/bin/env python3
"""三角分形（sierpinski）—— 谢尔宾斯基三角形/地毯的递归字符画生成。

用途:
    用递归细分算法生成谢尔宾斯基三角形（triangle）或
    谢尔宾斯基地毯（carpet）的字符画；--order 控制递归阶数，
    --char / --blank 自定义填充与空白字符。
    仅用 Python 标准库，单文件即可运行。

示例命令:
    python -I sierpinski.py --kind triangle --order 4
    python -I sierpinski.py --kind carpet --order 3
    python -I sierpinski.py --kind 三角 --order 5 --char @

参数:
    --kind    triangle|carpet|三角|地毯  分形类型（默认 triangle）
    --order N 递归阶数：三角形 0-7，地毯 0-4（默认 4）
    --char C  填充字符（默认 '#'）
    --blank C 空白字符（默认空格）
"""

import argparse
import sys

KIND_ALIASES = {
    "triangle": "triangle", "t": "triangle", "三角": "triangle",
    "carpet": "carpet", "c": "carpet", "地毯": "carpet",
}


def triangle_grid(order, char):
    rows = 2 ** order
    cols = 2 ** (order + 1)
    grid = [[" "] * cols for _ in range(rows)]

    def rec(o, r, c):
        if o == 0:
            grid[r][c] = char
            return
        half = 2 ** (o - 1)
        rec(o - 1, r, c)
        rec(o - 1, r + half, c - half)
        rec(o - 1, r + half, c + half)

    rec(order, 0, cols // 2)
    return grid


def carpet_grid(order, char, blank):
    n = 3 ** order
    grid = [[blank] * n for _ in range(n)]

    def rec(o, r, c):
        if o == 0:
            grid[r][c] = char
            return
        s = 3 ** (o - 1)
        for dr in (0, s, 2 * s):
            for dc in (0, s, 2 * s):
                if dr == s and dc == s:
                    continue  # 中央挖空
                rec(o - 1, r + dr, c + dc)

    rec(order, 0, 0)
    return grid


def build_parser():
    p = argparse.ArgumentParser(
        prog="sierpinski", description="谢尔宾斯基三角形/地毯的递归字符画生成"
    )
    p.add_argument("--kind", default="triangle",
                   help="类型: triangle|carpet 或 三角|地毯，默认 triangle")
    p.add_argument("--order", type=int, default=4, help="递归阶数（默认 4）")
    p.add_argument("--char", default="#", help="填充字符，默认 '#'")
    p.add_argument("--blank", default=" ", help="空白字符，默认空格")
    return p


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)

    kind = KIND_ALIASES.get(args.kind.strip().lower())
    if kind is None:
        print(f"错误: 无效类型 {args.kind!r}（可选: triangle|carpet 或 三角|地毯）",
              file=sys.stderr)
        return 2
    limits = {"triangle": (0, 7), "carpet": (0, 4)}
    lo, hi = limits[kind]
    if not (lo <= args.order <= hi):
        print(f"错误: --order 需在 {lo}-{hi} 之间（{kind}）", file=sys.stderr)
        return 2
    if len(args.char) != 1 or len(args.blank) != 1:
        print("错误: --char / --blank 各需恰好 1 个字符", file=sys.stderr)
        return 2

    if kind == "triangle":
        grid = triangle_grid(args.order, args.char)
    else:
        grid = carpet_grid(args.order, args.char, args.blank)

    print(f"# sierpinski {kind} order={args.order}"
          f" size={len(grid)}x{len(grid[0])}")
    for row in grid:
        print("".join(row).rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
