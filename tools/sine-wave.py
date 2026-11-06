#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""正弦波纹 —— 在终端里滚动播放正弦波 / 双波干涉动画。

示例命令:
    python sine-wave.py                                    # 行波动画, Ctrl+C 退出
    python sine-wave.py --mode interfere                   # 左右相向双波的干涉条纹
    python sine-wave.py --frames 5 --no-clear --delay 0.1  # 只播 5 帧不刷屏（测试/演示）
    python sine-wave.py --cols 80 --rows 14 --amp 4        # 指定画面尺寸与振幅
"""

import argparse
import math
import os
import shutil
import sys
import time

RAMP = ".:-=+*#%@"  # 振幅越大用越“重”的字符


def render_frame(cols, rows, t, mode, amp):
    """渲染一帧：每列按波形位移取一个字符。"""
    grid = [[" "] * cols for _ in range(rows)]
    mid = rows // 2
    for x in range(cols):
        fx = x / max(1, cols - 1)
        if mode == "interfere":
            # 左右两个波源相向而行：sin(kx-wt) + sin(kx+wt) => 驻波干涉条纹
            v = amp * 0.5 * (math.sin(2 * math.pi * (2 * fx - t))
                             + math.sin(2 * math.pi * (2 * fx + t)))
        else:
            # 行波叠加一个缓慢漂移的包络，更有流动感
            envelope = 0.6 + 0.4 * math.sin(2 * math.pi * (fx - 0.5 * t))
            v = amp * envelope * math.sin(2 * math.pi * (1.5 * fx - t))
        y = mid + int(round(v))
        if 0 <= y < rows:
            idx = int(abs(v) / max(1e-9, amp) * (len(RAMP) - 1))
            grid[y][x] = RAMP[max(0, min(len(RAMP) - 1, idx))]
    return "\n".join("".join(row).rstrip() for row in grid)


def enable_ansi():
    """尽最大努力开启 Windows 控制台的 ANSI 转义支持。"""
    if os.name == "nt":
        os.system("")
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass


def main(argv=None):
    ap = argparse.ArgumentParser(description="终端正弦波 / 干涉波滚动动画")
    ap.add_argument("--mode", choices=("wave", "interfere"), default="wave",
                    help="动画模式（默认 wave）")
    ap.add_argument("--frames", type=int, default=0,
                    help="播放帧数，0=无限循环直到 Ctrl+C（默认 0）")
    ap.add_argument("--delay", type=float, default=0.05, help="帧间隔秒数（默认 0.05）")
    ap.add_argument("--cols", type=int, default=0, help="画面宽度，默认取终端宽度")
    ap.add_argument("--rows", type=int, default=0, help="画面高度，默认取终端高度")
    ap.add_argument("--amp", type=int, default=0, help="振幅（行数），默认按画面高度自适应")
    ap.add_argument("--no-clear", action="store_true",
                    help="不清屏、逐帧追加输出（便于重定向查看/测试）")
    args = ap.parse_args(argv)

    size = shutil.get_terminal_size((66, 20))
    cols = args.cols or size.columns
    rows = args.rows or max(8, size.lines - 2)
    cols, rows = max(20, cols), max(6, rows)
    amp = args.amp or max(1, rows // 2 - 1)

    enable_ansi()
    t, frame = 0.0, 0
    try:
        while args.frames <= 0 or frame < args.frames:
            art = render_frame(cols, rows, t, args.mode, amp)
            if args.no_clear:
                if frame:
                    print()
                print(art)
            else:
                sys.stdout.write("\x1b[2J\x1b[H" + art + "\n")
            sys.stdout.flush()
            time.sleep(max(0.0, args.delay))
            t += 0.12
            frame += 1
    except KeyboardInterrupt:
        print("\n动画已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
