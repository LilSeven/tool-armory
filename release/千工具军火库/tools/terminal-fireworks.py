#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""terminal-fireworks（终端烟花）—— 随机位置逐帧绽放的 ANSI 彩色烟花表演。

烟花先从底部随机位置升空（火箭阶段），到达随机高度后炸开成一圈彩色
粒子；粒子受重力下坠、逐渐黯淡消散，同时不断有新烟花在随机位置升起。
支持 Ctrl+C 随时退出，退出时自动恢复终端；加 --frames 可限定帧数
（方便脚本与自测，也用于非交互管道环境）。

示例:
    python terminal-fireworks.py                    # 无限表演，Ctrl+C 退出
    python terminal-fireworks.py --fps 24 --max-active 6
    python terminal-fireworks.py --frames 15        # 只放 15 帧（脚本/自测友好）
    python terminal-fireworks.py --particles 60     # 每发烟花粒子更多

退出码: 0 正常结束或 Ctrl+C 退出；2 参数错误。
"""

import argparse
import ctypes
import math
import os
import random
import shutil
import sys
import time

RESET = "\033[0m"
COLORS = ("\033[91m", "\033[92m", "\033[93m", "\033[94m", "\033[95m", "\033[96m")
TRAIL_COLOR = "\033[33m"  # 火箭尾焰：黄色


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


def make_burst(x, y, color, count):
    """在一圈均匀方向上撒出 count 个粒子: [x, y, vx, vy, age, life, color]"""
    particles = []
    for i in range(count):
        angle = 2.0 * math.pi * i / count + random.uniform(-0.08, 0.08)
        speed = random.uniform(0.3, 1.0)
        particles.append([
            x, y,
            math.cos(angle) * speed,
            math.sin(angle) * speed,
            0,
            random.randint(12, 20),
            color,
        ])
    return particles


def build_parser():
    p = argparse.ArgumentParser(
        prog="terminal-fireworks",
        description="终端里随机位置逐帧绽放的 ANSI 彩色烟花表演（Ctrl+C 退出）。",
    )
    p.add_argument("--frames", type=int, default=0,
                   help="播放帧数，0 表示无限直到 Ctrl+C（默认 0）")
    p.add_argument("--fps", type=float, default=20.0, help="帧率（默认 20）")
    p.add_argument("--max-active", type=int, default=4,
                   help="同屏最多同时进行的烟花数（默认 4）")
    p.add_argument("--particles", type=int, default=36,
                   help="每发烟花的粒子数（默认 36）")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    force_utf8_stdio()
    if args.fps <= 0 or args.frames < 0 or args.max_active < 1 or args.particles < 4:
        print("错误：--fps 须为正、--frames 不能为负、--max-active 至少 1、--particles 至少 4。",
              file=sys.stderr)
        return 2
    enable_ansi()
    tty = sys.stdout.isatty()

    width, height = shutil.get_terminal_size((80, 24))
    cells = [[None] * width for _ in range(height)]  # 每格 [字符, 颜色, 剩余寿命帧数]
    rockets = []  # [x, y, target_y, 水平漂移, 颜色]
    bursts = []   # 每发炸开的粒子列表
    interval = 1.0 / args.fps
    frame = 0

    def resize():
        nonlocal width, height, cells
        width, height = shutil.get_terminal_size((80, 24))
        cells = [[None] * width for _ in range(height)]

    try:
        if tty:
            sys.stdout.write(RESET + "\033[2J\033[?25l")
        while args.frames <= 0 or frame < args.frames:
            t0 = time.monotonic()
            if shutil.get_terminal_size((width, height)) != (width, height):
                resize()
            # 1) 全屏余晖衰减
            for row in cells:
                for x, c in enumerate(row):
                    if c is not None:
                        c[2] -= 1
                        if c[2] <= 0:
                            row[x] = None
            # 2) 随机发射新火箭
            if len(rockets) + len(bursts) < args.max_active and random.random() < 0.3:
                rockets.append([
                    random.uniform(3.0, max(4.0, width - 4.0)),
                    float(height - 1),
                    random.uniform(2.0, max(4.0, height * 0.45)),
                    random.uniform(-0.12, 0.12),
                    random.choice(COLORS),
                ])
            # 3) 火箭上升，到顶后炸开
            for r in list(rockets):
                r[1] -= 1.1
                r[0] += r[3]
                iy, ix = int(r[1]), int(r[0])
                if 0 <= iy < height and 0 <= ix < width:
                    cells[iy][ix] = ["|", r[4], 1]
                    if iy + 1 < height:
                        cells[iy + 1][ix] = ["'", TRAIL_COLOR, 1]
                if r[1] <= r[2]:
                    rockets.remove(r)
                    bursts.append(make_burst(r[0], r[1], r[4], args.particles))
            # 4) 粒子运动（重力 + 阻尼），越界即弃
            for burst in list(bursts):
                alive = False
                for p in burst:
                    p[4] += 1
                    if p[4] > p[5]:
                        continue
                    p[0] += p[2]
                    p[1] += p[3]
                    p[3] += 0.045   # 重力
                    p[2] *= 0.985   # 空气阻尼
                    p[3] *= 0.985
                    iy, ix = int(p[1]), int(p[0])
                    if 0 <= iy < height and 0 <= ix < width:
                        alive = True
                        if p[4] < 2:
                            ch, color = "*", "\033[97m"  # 刚炸开时白热
                        elif p[4] < 8:
                            ch, color = "*", p[6]
                        elif p[4] < 14:
                            ch, color = "+", p[6]
                        else:
                            ch, color = ".", p[6]
                        cells[iy][ix] = [ch, color, 2]
                if not alive:
                    bursts.remove(burst)
            # 5) 渲染一帧
            rows = []
            for row in cells:
                pieces = []
                for c in row:
                    if c is None:
                        pieces.append(" ")
                    else:
                        pieces.append(c[1] + c[0] + RESET)
                rows.append("".join(pieces))
            if tty:
                sys.stdout.write("\033[H" + "\n".join(rows))
            else:
                sys.stdout.write("\n".join(rows) + "\n")
                print("[terminal-fireworks] frame %d" % (frame + 1), file=sys.stderr)
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
    print("烟花表演结束，共播放 %d 帧。" % frame)
    return 0


if __name__ == "__main__":
    sys.exit(main())
