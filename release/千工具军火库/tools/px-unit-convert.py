#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""像素单位换算 (px-unit-convert) —— 在指定 DPI 下进行像素与英寸/厘米/毫米的双向换算。

原理:
    像素(px) = 英寸(inch) x DPI；1 英寸 = 2.54 厘米 = 25.4 毫米。
给出 --px / --inch / --cm / --mm 四个选项中的任意一个，即换算出其余三个单位的结果。

示例命令:
    python px-unit-convert.py --dpi 300 --px 1024      # 1024 像素在 300DPI 下是多少英寸/厘米/毫米
    python px-unit-convert.py --dpi 300 --inch 2       # 2 英寸在 300DPI 下是多少像素
    python px-unit-convert.py --dpi 96  --cm 5         # 5 厘米在 96DPI 下是多少像素
    python px-unit-convert.py --dpi 300 --mm 25.4      # 25.4 毫米在 300DPI 下是多少像素

退出码: 0 成功; 2 参数错误（DPI 非法、输入为负等）。
"""

from __future__ import annotations

import argparse
import sys

MM_PER_INCH = 25.4
CM_PER_INCH = 2.54


def _setup_stdout() -> None:
    """Windows 管道/Git Bash 下尽量以 UTF-8 输出，避免中文乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def fmt(v: float, nd: int = 4) -> str:
    s = f"{v:.{nd}f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-", "-0") else s


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="px-unit-convert",
        description="在指定 DPI 下进行像素与英寸/厘米/毫米的双向换算。",
    )
    parser.add_argument("--dpi", type=float, required=True, help="DPI，必须大于 0，如 300")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--px", type=float, help="输入像素数")
    group.add_argument("--inch", type=float, help="输入英寸数")
    group.add_argument("--cm", type=float, help="输入厘米数")
    group.add_argument("--mm", type=float, help="输入毫米数")
    args = parser.parse_args(argv)

    if args.dpi <= 0:
        print("错误: --dpi 必须大于 0", file=sys.stderr)
        return 2

    if args.px is not None:
        label, value, unit = "像素 px", args.px, "px"
    elif args.inch is not None:
        label, value, unit = "英寸 inch", args.inch, "in"
    elif args.cm is not None:
        label, value, unit = "厘米 cm", args.cm, "cm"
    else:
        label, value, unit = "毫米 mm", args.mm, "mm"

    if value < 0:
        print("错误: 输入值不能为负数", file=sys.stderr)
        return 2

    to_inch = {
        "px": lambda v: v / args.dpi,
        "in": lambda v: v,
        "cm": lambda v: v / CM_PER_INCH,
        "mm": lambda v: v / MM_PER_INCH,
    }
    inch = to_inch[unit](value)
    px = inch * args.dpi
    cm = inch * CM_PER_INCH
    mm = inch * MM_PER_INCH

    print(f"DPI: {fmt(args.dpi)}")
    print(f"输入: {fmt(value)} {label}")
    print("-" * 32)
    print(f"像素 px  : {fmt(px)}")
    print(f"英寸 inch: {fmt(inch)}")
    print(f"厘米 cm  : {fmt(cm)}")
    print(f"毫米 mm  : {fmt(mm)}")
    return 0


if __name__ == "__main__":
    _setup_stdout()
    sys.exit(main())
