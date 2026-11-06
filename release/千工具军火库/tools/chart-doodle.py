#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""终端小图表 —— 把一串数字画成 ASCII 折线图 / 柱状图 / 散点图。

数字来源：位置参数、--data（逗号或空格分隔）、或 stdin 管道，可混用。
图表类型: line（折线, 默认）/ bar（柱状）/ scatter（散点）。

示例命令:
    python chart-doodle.py line 3 7 1 9 4
    python chart-doodle.py bar --data "5,2,8,4" --height 10
    python chart-doodle.py scatter 1 4 2 8 3 6
    seq 1 20 | python chart-doodle.py line
"""

import argparse
import sys


def fmt(v):
    """把数值格式成紧凑可读的刻度文本。"""
    return "%.4g" % v


def collect_numbers(args, ap):
    raw = list(args.numbers)
    if args.data:
        raw.append(args.data)
    tokens = " ".join(raw).replace(",", " ").split()
    if not tokens and not sys.stdin.isatty():
        tokens = sys.stdin.read().replace(",", " ").split()
    nums = []
    for tok in tokens:
        try:
            nums.append(float(tok))
        except ValueError:
            ap.error("无法解析的数字: %r" % tok)
    return nums


def _axes(grid, rows, width, lo, hi, labelw):
    """加左侧刻度与底部横轴，返回文本行列表。"""
    out = []
    for r in range(rows):
        label = fmt(hi) if r == 0 else (fmt(lo) if r == rows - 1 else "")
        out.append(label.rjust(labelw) + " |" + "".join(grid[r]).rstrip())
    out.append(" " * labelw + " +" + "-" * width)
    return out


def render_line(nums, height, width, scatter=False):
    lo, hi = min(nums), max(nums)
    if hi == lo:
        hi = lo + 1.0
    n = len(nums)
    rows = max(3, height)
    width = max(width, n) if scatter else max(width, 20)
    grid = [[" "] * width for _ in range(rows)]

    def yrow(v):
        frac = (v - lo) / (hi - lo)
        return max(0, min(rows - 1, int(round((rows - 1) * (1 - frac)))))

    if not scatter and n >= 2:
        for c in range(width):  # 逐列线性插值，画出连续折线
            t = c * (n - 1) / (width - 1)
            i = min(int(t), n - 2)
            v = nums[i] + (nums[i + 1] - nums[i]) * (t - i)
            grid[yrow(v)][c] = "*"
    for i, v in enumerate(nums):  # 数据点用 'o' 标出
        c = min(i * (width - 1) // (n - 1), width - 1) if n > 1 else 0
        grid[yrow(v)][c] = "o"
    out = _axes(grid, rows, width, lo, hi, max(len(fmt(lo)), len(fmt(hi))))
    kind = "散点" if scatter else "折线"
    out.append("%s图: %d 个点, 值域 [%s, %s]" % (kind, n, fmt(lo), fmt(hi)))
    return "\n".join(out)


def render_bar(nums, height, width):
    lo, hi = min(nums), max(nums)
    if hi == lo:
        hi = lo + 1.0
    n = len(nums)
    rows = max(3, height)
    bw = max(1, width // n - 1)          # 每根柱子的宽度
    gap = " " if bw > 1 else ""
    total = n * bw + (n - 1) * len(gap)

    def yrow(v):
        frac = (v - lo) / (hi - lo)
        return max(0, min(rows - 1, int(round((rows - 1) * (1 - frac)))))

    # 基线取 0（若 0 不在值域内则取最近的边界）
    baseline = min(max(0.0, lo), hi)
    yb = yrow(baseline)
    grid = [[" "] * total for _ in range(rows)]
    for i, v in enumerate(nums):
        c0 = i * (bw + len(gap))
        y = yrow(v)
        for r in range(min(y, yb), max(y, yb) + 1):
            for c in range(c0, c0 + bw):
                grid[r][c] = "#"
    out = _axes(grid, rows, total, lo, hi, max(len(fmt(lo)), len(fmt(hi))))
    out.append("柱状图: %d 根柱, 值域 [%s, %s], 基线 y=%s" % (n, fmt(lo), fmt(hi), fmt(baseline)))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="把数字序列画成 ASCII 折线图/柱状图/散点图")
    ap.add_argument("chart", nargs="?", default=None,
                    help="图表类型: line(默认)/bar/scatter")
    ap.add_argument("numbers", nargs="*", help="数字序列（空格分隔）")
    ap.add_argument("--data", default="", help="逗号或空格分隔的数字串, 如 \"5,2,8\"")
    ap.add_argument("--height", type=int, default=12, help="图高（行数, 默认 12）")
    ap.add_argument("--width", type=int, default=60, help="图宽（列数, 默认 60）")
    args = ap.parse_args(argv)

    charts = ("line", "bar", "scatter")
    if args.chart is None:
        args.chart = "line"
    elif args.chart not in charts:  # 容错: 第一个参数是数字时按 line 处理
        args.numbers.insert(0, args.chart)
        args.chart = "line"

    nums = collect_numbers(args, ap)
    if not nums:
        ap.error("没有可用的数字: 请用位置参数、--data 或 stdin 提供数字序列")
    if args.chart == "bar":
        art = render_bar(nums, args.height, args.width)
    else:
        art = render_line(nums, args.height, args.width,
                          scatter=(args.chart == "scatter"))
    print(art)
    return 0


if __name__ == "__main__":
    sys.exit(main())
