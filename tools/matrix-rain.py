#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""matrix-rain（字符雨）—— 黑客帝国风格的绿色字符雨终端动画，Ctrl+C 退出。

在支持 ANSI 转义序列的终端（Windows Terminal / Git Bash / 各类 Linux 终端）
中全屏播放：随机列上不断落下半角片假名与数字，头部亮白、拖尾由亮绿渐暗。
按 Ctrl+C 随时退出，退出时自动恢复终端配色与光标；加 --frames 可限定帧数
（方便脚本与自测，也用于非交互管道环境）。

示例:
    python matrix-rain.py                       # 无限播放，Ctrl+C 退出
    python matrix-rain.py --fps 24 --density 0.35
    python matrix-rain.py --frames 10           # 只播 10 帧（脚本/自测友好）
    python matrix-rain.py --charset "01ABC"     # 自定义雨滴字符集

退出码: 0 正常结束或 Ctrl+C 退出；2 参数错误。
"""

import argparse
import ctypes
import os
import random
import shutil
import sys
import time

RESET = "\033[0m"
HEAD_COLOR = "\033[1;97m"  # 雨滴头部：亮白


def force_utf8_stdio():
    """输出流编码非 UTF-8 时（如 Windows 管道默认 GBK）切到 UTF-8，避免乱码或报错。"""
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
            if enc and enc != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def enable_ansi():
    """尽力开启 Windows 控制台的 VT 转义序列支持，非 Windows 或失败时静默跳过。"""
    if os.name != "nt":
        return
    os.system("")  # 触发控制台初始化，常见的小技巧
    try:
        k32 = ctypes.windll.kernel32
        handle = k32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if k32.GetConsoleMode(handle, ctypes.byref(mode)):
            k32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass


def build_parser():
    p = argparse.ArgumentParser(
        prog="matrix-rain",
        description="黑客帝国绿色字符雨动画（Ctrl+C 退出）。",
    )
    p.add_argument("--frames", type=int, default=0,
                   help="播放帧数，0 表示无限直到 Ctrl+C（默认 0）")
    p.add_argument("--fps", type=float, default=18.0, help="帧率（默认 18）")
    p.add_argument("--density", type=float, default=0.18,
                   help="每个空列出现新雨滴的概率 0~1（默认 0.18）")
    p.add_argument("--charset",
                   default="ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789",
                   help="雨滴字符集（默认半角片假名+数字，保证等宽对齐）")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    force_utf8_stdio()
    if args.fps <= 0 or args.frames < 0 or not (0.0 <= args.density <= 1.0):
        print("错误：--fps 必须为正、--frames 不能为负、--density 须在 0~1 之间。",
              file=sys.stderr)
        return 2
    charset = args.charset
    if not charset:
        print("错误：--charset 不能为空。", file=sys.stderr)
        return 2
    enable_ansi()
    tty = sys.stdout.isatty()

    width, height = shutil.get_terminal_size((80, 24))
    chars = [[" "] * width for _ in range(height)]   # 每格雨滴字符
    levels = [[0] * width for _ in range(height)]    # 每格亮度 0~3
    heads = {}  # 列号 -> (y 浮点位置, 速度)
    interval = 1.0 / args.fps
    frame = 0

    def resize():
        nonlocal width, height, chars, levels
        width, height = shutil.get_terminal_size((80, 24))
        chars = [[" "] * width for _ in range(height)]
        levels = [[0] * width for _ in range(height)]

    try:
        if tty:
            sys.stdout.write(RESET + "\033[2J\033[?25l")
        while args.frames <= 0 or frame < args.frames:
            t0 = time.monotonic()
            if shutil.get_terminal_size((width, height)) != (width, height):
                resize()
            # 1) 拖尾整体衰减一格
            for row in levels:
                for x, v in enumerate(row):
                    if v:
                        row[x] = v - 1
            # 2) 雨滴前进、补拖尾、随机生成新雨滴
            for x in range(width):
                drop = heads.get(x)
                if drop is None:
                    if random.random() < args.density:
                        heads[x] = [random.uniform(-height, 0.0), random.uniform(0.7, 2.2)]
                    continue
                drop[0] += drop[1]
                iy = int(drop[0])
                if 0 <= iy < height:
                    chars[iy][x] = random.choice(charset)
                    levels[iy][x] = 3
                for k in (1, 2, 3):  # 速度>1 时补上跳过的格子
                    yy = iy - k
                    if 0 <= yy < height and levels[yy][x] == 0:
                        levels[yy][x] = max(3 - k, 1)
                if drop[0] >= height + 4:
                    del heads[x]
            # 3) 渲染一帧
            rows = []
            for y in range(height):
                ch_row, lv_row = chars[y], levels[y]
                pieces = []
                for x in range(width):
                    v = lv_row[x]
                    if v >= 3:
                        pieces.append(HEAD_COLOR + ch_row[x])
                    elif v == 2:
                        pieces.append("\033[1;92m" + ch_row[x])
                    elif v == 1:
                        pieces.append("\033[32m" + ch_row[x])
                    else:
                        pieces.append(" ")
                rows.append("".join(pieces) + RESET if tty else "".join(pieces))
            if tty:
                sys.stdout.write("\033[H" + "\n".join(rows))
            else:
                sys.stdout.write("\n".join(rows) + "\n")
                print("[matrix-rain] frame %d" % (frame + 1), file=sys.stderr)
            sys.stdout.flush()
            frame += 1
            delay = interval - (time.monotonic() - t0)
            if delay > 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(RESET)
        if tty:
            sys.stdout.write("\033[?25h")
        sys.stdout.flush()
    print("雨停了，共播放 %d 帧。" % frame)
    return 0


if __name__ == "__main__":
    sys.exit(main())
