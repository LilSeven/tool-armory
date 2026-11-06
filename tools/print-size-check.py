#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冲印尺寸检查 (print-size-check) —— 按 300DPI 标准判断照片长边可冲印的最大尺寸并给出推荐规格。

把照片像素尺寸按输入 DPI（默认 300，冲印行业标准）换算成可冲印的物理尺寸，对照常见
冲印规格（5寸/6寸/7寸/8寸/10寸、A6/A5/A4/A3/A3+）给出:
  1) 可冲印的最大物理尺寸（含长边）;
  2) 全部可满足的规格（照片两条边都不小于该规格即可，横竖不限）;
  3) 其中最高规格（长边最大者），以及未满足的规格。

示例命令:
    python print-size-check.py 3000x2250              # 按 300DPI 估算
    python print-size-check.py 1500x2100 --dpi 300    # 竖版照片（5x7 寸）
    python print-size-check.py 4032x3024 --dpi 240    # 按 240DPI 估算

退出码: 0 成功（含“无规格可满足”的情况）; 2 参数错误。
"""

from __future__ import annotations

import argparse
import sys

MM_PER_INCH = 25.4
EPS = 1e-6  # 英寸容差（约 0.003mm），用于对消浮点误差

# (规格名, 标称长边英寸, 标称短边英寸, 标称毫米标注)
SPECS = [
    ("5寸 (3R)", 5.0, 3.5, "127x89mm"),
    ("6寸 (4R)", 6.0, 4.0, "152x102mm"),
    ("7寸 (5R)", 7.0, 5.0, "178x127mm"),
    ("8寸 (6R)", 8.0, 6.0, "203x152mm"),
    ("10寸 (8R)", 10.0, 8.0, "254x203mm"),
    ("A6", 148 / MM_PER_INCH, 105 / MM_PER_INCH, "148x105mm"),
    ("A5", 210 / MM_PER_INCH, 148 / MM_PER_INCH, "210x148mm"),
    ("A4", 297 / MM_PER_INCH, 210 / MM_PER_INCH, "297x210mm"),
    ("A3", 420 / MM_PER_INCH, 297 / MM_PER_INCH, "420x297mm"),
    ("A3+", 483 / MM_PER_INCH, 329 / MM_PER_INCH, "483x329mm"),
]


def _setup_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def fmt(v: float, nd: int = 4) -> str:
    s = f"{v:.{nd}f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-", "-0") else s


def parse_size(text: str):
    s = text.strip().lower().replace("×", "x").replace("*", "x")
    parts = s.split("x")
    if len(parts) != 2:
        raise ValueError(f"尺寸格式应为 宽x高，如 3000x2250，收到: {text!r}")
    try:
        w, h = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"像素尺寸必须为正整数，收到: {text!r}") from None
    if w <= 0 or h <= 0:
        raise ValueError("像素尺寸必须为正数")
    return w, h


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="print-size-check",
        description="按 300DPI 标准判断照片长边可冲印的最大尺寸并给出推荐规格。",
    )
    parser.add_argument("size", help="照片像素尺寸，格式 宽x高，如 3000x2250")
    parser.add_argument("--dpi", type=float, default=300, help="估算用 DPI，默认 300")
    args = parser.parse_args(argv)

    try:
        w, h = parse_size(args.size)
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    if args.dpi <= 0:
        print("错误: --dpi 必须大于 0", file=sys.stderr)
        return 2

    w_in, h_in = w / args.dpi, h / args.dpi
    long_in, short_in = max(w_in, h_in), min(w_in, h_in)

    print(f"照片像素: {w} x {h} @ {fmt(args.dpi)} DPI")
    print(
        f"可冲印物理尺寸: {fmt(w_in)} x {fmt(h_in)} 英寸 "
        f"({fmt(w_in * 2.54)} x {fmt(h_in * 2.54)} cm / "
        f"{fmt(w_in * MM_PER_INCH)} x {fmt(h_in * MM_PER_INCH)} mm)"
    )
    print(f"长边最大可冲印: {fmt(long_in)} 英寸 ({fmt(long_in * 2.54)} cm)")

    fitting, missing = [], []
    for name, spec_long, spec_short, mm_label in SPECS:
        if long_in >= spec_long - EPS and short_in >= spec_short - EPS:
            fitting.append((name, spec_long, spec_short, mm_label))
        else:
            missing.append(name)

    print()
    if not fitting:
        print("可满足的规格: 无 —— 该照片未达到任何标准冲印规格（仅适合屏幕显示）")
        return 0

    fitting.sort(key=lambda t: t[1])
    best = fitting[-1]
    print("可满足的冲印规格 (标称长x短边):")
    for name, sl, ss, mm_label in fitting:
        mark = "   <-- 最高规格" if name == best[0] else ""
        print(f"  [OK] {name:<10} {fmt(sl, 4):>8} x {fmt(ss, 4):<8} 英寸 ({mm_label}){mark}")
    if missing:
        print(f"未满足的规格: {', '.join(missing)}")
    print(f"结论: 按 {fmt(args.dpi)} DPI 最高可冲印 {best[0]}（标称长边 {fmt(best[1])} 英寸）。")
    return 0


if __name__ == "__main__":
    _setup_stdout()
    sys.exit(main())
