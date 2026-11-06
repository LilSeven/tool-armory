#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""treemap-ascii — ASCII 矩形树图。

把目录占用画成字符版矩形树图(treemap): 根目录下每个条目占一块矩形,
面积与大小成正比, squarified 算法让矩形尽量接近正方形, 整体俯视磁盘构成。
纯 ASCII 字符('+' '-' '|' 与填充符)绘制, 任何终端与编码都能正常显示。
只画根目录的第一层; 各条目的名称/大小/占比见可关闭的图例。

示例:
    python -I treemap-ascii.py D:\\data                 # 默认 80x24
    python -I treemap-ascii.py . --width 60 --height 18 # 自定义画布
    python -I treemap-ascii.py . --no-legend            # 只画图不加图例

退出码: 0 成功(空目录给出提示); 1 目录不存在。
"""

import argparse
import os
import shutil
import sys
import unicodedata

FILLS = ".:oO*x#"


def dwidth(text):
    return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
               for ch in text)


def clip(text, width):
    """按显示宽度截断字符串(CJK 全角按 2 计)。"""
    out = []
    used = 0
    for ch in text:
        w = 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
        if used + w > width:
            break
        out.append(ch)
        used += w
    return "".join(out)


def pad(text, width, align="left"):
    gap = max(width - dwidth(text), 0)
    if align == "right":
        return " " * gap + text
    return text + " " * gap


def human(num, space=True):
    val = float(num)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if val < 1024 or unit == "PiB":
            if unit == "B":
                return ("%d" % int(val)) + (" " if space else "") + unit
            return ("%.1f" % val) + (" " if space else "") + unit
        val /= 1024.0


def dir_size(path):
    """递归统计目录: 返回 (总字节, 文件数, 错误数)。"""
    total = files = errors = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            entries = os.scandir(current)
        except OSError:
            errors += 1
            continue
        with entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                        files += 1
                except OSError:
                    errors += 1
    return total, files, errors


def squarify(areas, x, y, dx, dy):
    """squarified treemap。areas 需按降序排列且总和 == dx*dy。返回 [(x, y, w, h)]。"""

    def emit(row, x, y, dx, dy):
        s = float(sum(row))
        out = []
        if dx >= dy:
            thick = s / dy if dy > 0 else 0.0
            cy = y
            for v in row:
                h = v / thick if thick > 0 else 0.0
                out.append((x, cy, thick, h))
                cy += h
            return out, (x + thick, y, dx - thick, dy)
        thick = s / dx if dx > 0 else 0.0
        cx = x
        for v in row:
            w = v / thick if thick > 0 else 0.0
            out.append((cx, y, w, thick))
            cx += w
        return out, (x, y + thick, dx, dy - thick)

    def worst(row, side):
        s = float(sum(row))
        if s <= 0 or side <= 0:
            return float("inf")
        vmax, vmin = max(row), min(row)
        return max(side * side * vmax / (s * s), s * s / (side * side * vmin))

    rects = []
    row = []
    i, n = 0, len(areas)
    while i < n:
        side = min(dx, dy)
        if not row:
            row = [areas[i]]
            i += 1
            continue
        if worst(row + [areas[i]], side) <= worst(row, side):
            row.append(areas[i])
            i += 1
        else:
            out, (x, y, dx, dy) = emit(row, x, y, dx, dy)
            rects.extend(out)
            row = []
            if dx <= 1e-9 or dy <= 1e-9:
                return rects
    if row:
        out, _ = emit(row, x, y, dx, dy)
        rects.extend(out)
    return rects


def render(rects, labels, width, height):
    grid = [[" "] * width for _ in range(height)]
    for idx, (rx, ry, rw, rh) in enumerate(rects):
        x1 = max(0, min(width, int(round(rx))))
        y1 = max(0, min(height, int(round(ry))))
        x2 = max(0, min(width, int(round(rx + rw))))
        y2 = max(0, min(height, int(round(ry + rh))))
        if x2 - x1 < 1 or y2 - y1 < 1:
            continue
        fill = FILLS[idx % len(FILLS)]
        if x2 - x1 < 3 or y2 - y1 < 3:
            for yy in range(y1, y2):
                for xx in range(x1, x2):
                    grid[yy][xx] = fill
            continue
        for yy in range(y1, y2):
            top = yy == y1
            bottom = yy == y2 - 1
            for xx in range(x1, x2):
                left = xx == x1
                right = xx == x2 - 1
                if (top or bottom) and (left or right):
                    ch = "+"
                elif top or bottom:
                    ch = "-"
                elif left or right:
                    ch = "|"
                else:
                    ch = fill
                grid[yy][xx] = ch
        name, pct = labels[idx]
        inner_w = x2 - x1 - 2
        if inner_w >= 1:
            text = clip(name, inner_w)
            for j, ch in enumerate(text):
                grid[y1 + 1][x1 + 1 + j] = ch
            if y2 - y1 >= 4 and inner_w >= 3:
                ptext = clip("%.1f%%" % pct, inner_w)
                for j, ch in enumerate(ptext):
                    grid[y1 + 2][x1 + 1 + j] = ch
    return "\n".join("".join(row) for row in grid)


def render_legend(entries, total, limit=15, name_w=24):
    lines = ["#  %s  %10s  pct" % (pad("name", name_w), "size")]
    for i, item in enumerate(entries[:limit], 1):
        lines.append("%-2d %s  %10s  %5.1f%%" % (
            i, pad(clip(item["name"], name_w), name_w),
            human(item["size"]), 100.0 * item["size"] / total))
    if len(entries) > limit:
        lines.append("... %d more entries" % (len(entries) - limit))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="treemap-ascii",
        description="把目录占用画成字符版矩形树图, 面积对应大小比例, 整体俯视磁盘构成。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n  python -I treemap-ascii.py D:\\data --width 60 --height 18")
    parser.add_argument("path", nargs="?", default=".",
                        help="要可视化的目录 (默认当前目录)")
    parser.add_argument("--width", type=int, default=None,
                        help="画布宽, 字符列数 (默认 80, tty 下取终端宽)")
    parser.add_argument("--height", type=int, default=None,
                        help="画布高, 字符行数 (默认 24, tty 下取终端高)")
    parser.add_argument("--no-legend", action="store_true", help="不显示图例")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    root = args.path
    if not os.path.isdir(root):
        print("目录不存在: %s" % root, file=sys.stderr)
        return 1

    if args.width:
        width = args.width
    elif sys.stdout.isatty():
        width = max(shutil.get_terminal_size((80, 24)).columns, 40)
    else:
        width = 80
    if args.height:
        height = args.height
    elif sys.stdout.isatty():
        height = max(shutil.get_terminal_size((80, 24)).lines - 2, 10)
    else:
        height = 24

    entries = []
    total = 0
    files = 0
    errors = 0
    try:
        entries_iter = os.scandir(root)
    except OSError as exc:
        print("无法读取目录: %s (%s)" % (root, exc), file=sys.stderr)
        return 1
    with entries_iter:
        for entry in entries_iter:
            try:
                if entry.is_dir(follow_symlinks=False):
                    size, n_files, n_errors = dir_size(entry.path)
                    files += n_files
                    errors += n_errors
                elif entry.is_file(follow_symlinks=False):
                    size = entry.stat(follow_symlinks=False).st_size
                    files += 1
                else:
                    continue
            except OSError:
                errors += 1
                continue
            entries.append({"name": entry.name, "size": size})
            total += size

    if not entries or total <= 0:
        print("目录为空或所有条目大小都是 0: %s" % os.path.abspath(root))
        return 0

    entries.sort(key=lambda e: -e["size"])
    mappable = [e for e in entries if e["size"] > 0]
    areas = [e["size"] * width * height / float(total) for e in mappable]
    rects = squarify(areas, 0.0, 0.0, float(width), float(height))
    labels = [(e["name"], 100.0 * e["size"] / total) for e in mappable]

    print("root=%s  total=%s  files=%d%s" % (
        root, human(total), files, ("  scan_errors=%d" % errors) if errors else ""))
    print(render(rects, labels, width, height))
    if not args.no_legend:
        print(render_legend(entries, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
