#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DPI 需求反推 (dpi-requirement-calc) —— 已知目标物理打印尺寸与目标 DPI，反推所需的最小像素尺寸。

计算公式: 所需像素 = 物理尺寸(英寸) x DPI，结果向上取整，保证不低于目标精度。

示例命令:
    python dpi-requirement-calc.py --inch 8x6 --dpi 300     # 8x6 英寸照片 @300DPI
    python dpi-requirement-calc.py --cm 21x29.7 --dpi 300   # A4 纸 @300DPI
    python dpi-requirement-calc.py --mm 210x297 --dpi 150   # A4 纸 @150DPI
    python dpi-requirement-calc.py --inch 4 --dpi 600       # 4x4 英寸正方形 @600DPI

尺寸格式: 宽x高（支持小数），只给一个数表示正方形，如 --inch 4 表示 4x4 英寸。

退出码: 0 成功; 2 参数错误（DPI 非法、尺寸非法等）。
"""

from __future__ import annotations

import argparse
import math
import sys

MM_PER_INCH = 25.4
CM_PER_INCH = 2.54


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


def parse_dims(text: str):
    """解析 '宽x高' 或单个数值（正方形），返回 (宽, 高) 的浮点数。"""
    s = text.strip().lower().replace("×", "x").replace("*", "x")
    parts = [p for p in s.split("x") if p != ""]
    if len(parts) == 1:
        parts = [parts[0], parts[0]]
    if len(parts) != 2:
        raise ValueError(f"尺寸格式应为 宽x高 或 单个数值，收到: {text!r}")
    try:
        w, h = float(parts[0]), float(parts[1])
    except ValueError:
        raise ValueError(f"尺寸数值不合法: {text!r}") from None
    if not (math.isfinite(w) and math.isfinite(h)) or w <= 0 or h <= 0:
        raise ValueError("尺寸必须为有限的正数")
    return w, h


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="dpi-requirement-calc",
        description="已知目标物理打印尺寸与目标 DPI，反推所需的最小像素尺寸。",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--inch", help="目标尺寸（英寸），如 8x6 或 4")
    group.add_argument("--cm", help="目标尺寸（厘米），如 21x29.7")
    group.add_argument("--mm", help="目标尺寸（毫米），如 210x297")
    parser.add_argument("--dpi", type=float, required=True, help="目标 DPI，必须大于 0，如 300")
    args = parser.parse_args(argv)

    if args.dpi <= 0:
        print("错误: --dpi 必须大于 0", file=sys.stderr)
        return 2

    try:
        if args.inch is not None:
            w, h = parse_dims(args.inch)
            unit, inch_w, inch_h = "英寸", w, h
        elif args.cm is not None:
            w, h = parse_dims(args.cm)
            unit, inch_w, inch_h = "厘米", w / CM_PER_INCH, h / CM_PER_INCH
        else:
            w, h = parse_dims(args.mm)
            unit, inch_w, inch_h = "毫米", w / MM_PER_INCH, h / MM_PER_INCH
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    exact_w, exact_h = inch_w * args.dpi, inch_h * args.dpi
    # 减去极小 epsilon，避免 2400.0 这类本应为整数的值因浮点误差被取整到 2401
    need_w = math.ceil(exact_w - 1e-9)
    need_h = math.ceil(exact_h - 1e-9)

    print(f"目标物理尺寸: {fmt(w)} x {fmt(h)} {unit} ({fmt(inch_w)} x {fmt(inch_h)} 英寸)")
    print(f"目标 DPI: {fmt(args.dpi)}")
    print(f"精确像素需求: {fmt(exact_w, 2)} x {fmt(exact_h, 2)}")
    print(f"所需最小像素: {need_w} x {need_h} （按 {fmt(args.dpi)} DPI 向上取整）")
    return 0


if __name__ == "__main__":
    _setup_stdout()
    sys.exit(main())
