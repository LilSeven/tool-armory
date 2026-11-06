#!/usr/bin/env python3
"""抽签排座（group-seat-draw）——生成教室/会议的随机座位安排表（文本版座位图）。

用途：班级/培训/会议/聚餐随机排座位，输出带边框的文本座位图，可直接贴到群里。

示例命令：
  python group-seat-draw.py names.txt --rows 4 --cols 6     # 4 排 6 列座位图
  python group-seat-draw.py names.txt --cols 5              # 只给列数，行数自动算
  cat names.txt | python group-seat-draw.py --rows 3 --cols 4    # 名单走 stdin
  python group-seat-draw.py --count 12 --cols 4             # 无名单时用「嘉宾1..N」
  python group-seat-draw.py names.txt --rows 2 --cols 4 --seed 42  # 固定种子复现

名单文件：每行一个名字；空行与 # 开头的注释行忽略；自动识别 utf-8 / gbk。
座位总数 rows*cols 必须不少于人数，多出的座位显示为「空」；
只给 rows 或 cols 之一时另一个按人数自动算，都不给时按近方形排布。
退出码：0 成功；2 参数或输入错误（名单为空、座位不够等）。
仅依赖 Python 标准库。
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path


def _utf8_stdio() -> None:
    """Windows 控制台/管道下强制 UTF-8 输出，避免中文乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _read_text(src: str) -> str:
    """读入文本，依次尝试 utf-8 / gbk 解码；'-' 表示 stdin。"""
    data = sys.stdin.buffer.read() if src == "-" else Path(src).read_bytes()
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _display_width(s: str) -> int:
    """近似终端显示宽度：中日韩全角字符按 2 列计，其余按 1 列。"""
    w = 0
    for ch in s:
        o = ord(ch)
        wide = (0x1100 <= o <= 0x115F or 0x2E80 <= o <= 0xA4CF
                or 0xAC00 <= o <= 0xD7A3 or 0xF900 <= o <= 0xFAFF
                or 0xFE30 <= o <= 0xFE4F or 0xFF00 <= o <= 0xFF60
                or 0xFFE0 <= o <= 0xFFE6)
        w += 2 if wide else 1
    return w


def _pad(s: str, width: int) -> str:
    """按显示宽度右侧补空格，保证中文混排时边框对齐。"""
    return s + " " * max(0, width - _display_width(s))


def _render_map(rows: int, cols: int, seats: list[str]) -> list[str]:
    """渲染带边框的文本座位图（含顶部讲台行）。"""
    cells = [[f"{r * cols + c + 1} {seats[r * cols + c]}" for c in range(cols)]
             for r in range(rows)]
    colw = [max(_display_width(cells[r][c]) for r in range(rows)) + 2
            for c in range(cols)]
    label_w = max(_display_width(f"第{r}排") for r in range(1, rows + 1))
    margin = " " * (label_w + 1)
    inner = sum(colw) + (cols - 1)

    def border(left: str, mid: str, right: str) -> str:
        return margin + left + mid.join("─" * w for w in colw) + right

    title = "讲 台"
    lead = max(0, (inner - _display_width(title)) // 2)
    lines = [" " * (label_w + 1 + lead) + title, border("┌", "┬", "┐")]
    for r in range(rows):
        row = "│".join(" " + _pad(cells[r][c], colw[c] - 2) + " "
                       for c in range(cols))
        lines.append(f"{_pad(f'第{r + 1}排', label_w)} │{row}│")
        if r < rows - 1:
            lines.append(border("├", "┼", "┤"))
    lines.append(border("└", "┴", "┘"))
    return lines


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="group-seat-draw",
        description="生成教室/会议的随机座位安排表（文本版座位图）。",
    )
    parser.add_argument("names_file", nargs="?", default=None,
                        help="名单文件（每行一个名字）；缺省表示从 stdin 读")
    parser.add_argument("--rows", type=int, help="座位排数")
    parser.add_argument("--cols", type=int, help="座位列数")
    parser.add_argument("--count", type=int, metavar="N",
                        help="不提供名单时，直接生成 嘉宾1..N 共 N 人")
    parser.add_argument("--seed", type=int, help="随机种子（相同种子结果可复现）")
    args = parser.parse_args(argv)

    if args.count is not None:
        if args.count < 1:
            print("错误：--count 必须 ≥ 1。", file=sys.stderr)
            return 2
        names = [f"嘉宾{i}" for i in range(1, args.count + 1)]
    else:
        src = args.names_file or "-"
        if src != "-" and not Path(src).is_file():
            print(f"错误：找不到名单文件 {src}", file=sys.stderr)
            return 2
        raw_names = [s.strip() for s in _read_text(src).splitlines()]
        names = [s for s in raw_names if s and not s.startswith("#")]

    n = len(names)
    if n == 0:
        print("错误：名单为空，无法排座。", file=sys.stderr)
        return 2

    rows, cols = args.rows, args.cols
    if rows is None and cols is None:
        cols = max(1, math.ceil(math.sqrt(n)))
        rows = math.ceil(n / cols)
    elif rows is None:
        if cols < 1:
            print("错误：--cols 必须 ≥ 1。", file=sys.stderr)
            return 2
        rows = math.ceil(n / cols)
    elif cols is None:
        if rows < 1:
            print("错误：--rows 必须 ≥ 1。", file=sys.stderr)
            return 2
        cols = math.ceil(n / rows)
    if rows < 1 or cols < 1:
        print("错误：--rows / --cols 必须 ≥ 1。", file=sys.stderr)
        return 2
    if rows * cols < n:
        print(f"错误：座位 {rows}×{cols}={rows * cols} 个，少于人数 {n}。",
              file=sys.stderr)
        return 2

    random.Random(args.seed).shuffle(names)
    seats = names + ["空"] * (rows * cols - n)

    seed_text = f"（随机种子 {args.seed}）" if args.seed is not None else ""
    print(f"抽签排座结果：共 {n} 人，{rows} 排 × {cols} 列{seed_text}")
    print("\n".join(_render_map(rows, cols, seats)))
    print("说明：座位号自第 1 排（靠讲台）左起编号；「空」为多余座位。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
