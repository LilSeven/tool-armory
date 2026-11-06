#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""star-field 星际穿越 —— 星星向外飞掠的伪 3D 隧道动画。

用途：
    生成一批带随机平面坐标 (x, y) 与深度 z 的星星，每帧让 z 不断
    减小（星星逼近观察者），按透视投影到屏幕：越近的星星离中心越
    远、字符越亮，飞出屏幕后从深处重生，形成穿越星空隧道的观感。
    按 Ctrl+C 退出；输出被重定向时逐帧打印，便于测试与录制。

示例命令：
    python star-field.py                            # 默认 120 颗星，无限循环
    python star-field.py --stars 200 --speed 0.08   # 更多更快的星星
    python star-field.py --frames 30 --seed 42      # 固定种子跑 30 帧（自测用）
    python star-field.py --width 60 --height 15 --frames 10
"""

import argparse
import os
import random
import shutil
import sys
import time

DEPTH_CHARS = "..::+**@@"  # 越靠后越“近”越亮
MIN_Z = 0.05


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="星际穿越：星星向外飞掠的伪 3D 隧道动画")
    parser.add_argument("--stars", type=int, default=120, help="星星数量（默认 120）")
    parser.add_argument("--speed", type=float, default=0.08,
                        help="每帧深度推进比例（默认 0.08）")
    parser.add_argument("--delay", type=float, default=0.04, help="帧间隔秒数（默认 0.04）")
    parser.add_argument("--frames", type=int, default=0, help="最大帧数，0=无限（默认 0）")
    parser.add_argument("--seed", type=int, default=None, help="随机数种子（便于复现）")
    parser.add_argument("--width", type=int, default=0, help="画布宽度，0=自动（默认 0）")
    parser.add_argument("--height", type=int, default=0, help="画布高度，0=自动（默认 0）")
    return parser.parse_args(argv)


def canvas_size(args):
    cols, rows = shutil.get_terminal_size(fallback=(80, 24))
    return args.width or max(20, cols), args.height or max(8, rows - 1)


def new_star(rng):
    while True:
        x, y = rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0)
        if x * x + y * y <= 1.0:
            return {"x": x, "y": y, "z": 1.0}


def render_frame(stars, width, height, frame_no):
    grid = [[" "] * width for _ in range(height)]
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    for st in stars:
        z = st["z"]
        if z <= MIN_Z:
            continue
        px = int(round(cx + st["x"] / z * cx))
        py = int(round(cy + st["y"] / z * cy * 0.5))  # 终端字符高宽比约 2:1
        if 0 <= px < width and 0 <= py < height:
            depth = min(1.0, max(0.0, 1.0 - z))
            ch = DEPTH_CHARS[min(int(depth * len(DEPTH_CHARS)), len(DEPTH_CHARS) - 1)]
            grid[py][px] = ch
    return "\n".join("".join(row) for row in grid) + \
        "\n[frame %4d] stars=%d" % (frame_no, len(stars))


def main(argv=None):
    args = parse_args(argv)
    if os.name == "nt":
        os.system("")  # 让 Windows 控制台启用 ANSI 转义序列
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    width, height = canvas_size(args)
    rng = random.Random(args.seed)
    stars = []
    for _ in range(max(1, args.stars)):
        st = new_star(rng)
        st["z"] = rng.uniform(MIN_Z, 1.0)
        stars.append(st)
    speed = min(0.5, max(0.01, args.speed))
    plain = not sys.stdout.isatty()
    frame = 0
    try:
        if not plain:
            sys.stdout.write("\x1b[2J")  # 清屏一次
        while args.frames <= 0 or frame < args.frames:
            body = render_frame(stars, width, height, frame)
            if plain:
                sys.stdout.write(body + "\n\n")
            else:
                sys.stdout.write("\x1b[H" + body + "\n")
            sys.stdout.flush()
            for st in stars:
                st["z"] -= st["z"] * speed
                if st["z"] <= MIN_Z:
                    st.update(new_star(rng))
            frame += 1
            if args.delay > 0:
                time.sleep(args.delay)
    except KeyboardInterrupt:
        pass
    finally:
        if not plain:
            sys.stdout.write("\x1b[%d;1H" % (height + 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
