#!/usr/bin/env python3
"""曼德博画卷（mandelbrot-ascii）—— 在终端打印曼德博集合字符画。

用途:
    逐点迭代 z <- z^2 + c 计算曼德博集合，按逃逸速度映射为字符灰度，
    在终端打印字符画；支持指定中心/视野缩放区域与内置预设机位。
    仅用 Python 标准库，单文件即可运行（纯 float 运算，
    缩放 scale 小于约 1e-4 时精度有限，会有失真提示）。

示例命令:
    python -I mandelbrot-ascii.py --width 64
    python -I mandelbrot-ascii.py --preset seahorse --width 72
    python -I mandelbrot-ascii.py --cx -0.7453 --cy 0.1127 --scale 0.01 --width 80 --max-iter 300
    python -I mandelbrot-ascii.py --preset valley --width 60 --chars " .:*#"

参数:
    --width N     画布宽（10-240，默认 72）
    --height N    画布高（默认按终端字符纵横比自动 ≈ width*0.44）
    --cx / --cy   视野中心（默认 -0.6 / 0.0）
    --scale F     视野半宽（实轴范围 [-scale, +scale]，默认 1.5）
    --max-iter N  最大迭代数（>=10，默认 150）
    --preset NAME 预设机位: full|valley|seahorse|elephant|spiral（覆盖 cx/cy/scale）
    --chars STR   由暗到亮的字符梯度（默认 ' .:-=+*#%@'，集合内部用最后一位）
"""

import argparse
import math
import sys

PRESETS = {
    "full":     (-0.6, 0.0, 1.5),
    "valley":   (-0.75, 0.1, 0.1),
    "seahorse": (-0.743643887, 0.131825904, 0.005),
    "elephant": (-0.235125, 0.827215, 0.01),
    "spiral":   (-0.7269, 0.1889, 0.0008),
}


def render(cx, cy, scale, width, height, max_iter, chars):
    x0 = cx - scale
    step_x = (2 * scale) / (width - 1)
    step_y = step_x * 2.0  # 终端字符高约为宽的 2 倍
    y0 = cy + step_y * (height - 1) / 2.0
    interior = chars[-1]
    lines = []
    for row in range(height):
        y = y0 - row * step_y
        line = []
        for col in range(width):
            x = x0 + col * step_x
            zr = zi = 0.0
            i = 0
            while i < max_iter and zr * zr + zi * zi <= 4.0:
                zr, zi = zr * zr - zi * zi + x, 2.0 * zr * zi + y
                i += 1
            if i >= max_iter:
                line.append(interior)
            else:
                t = math.sqrt(i / max_iter)
                line.append(chars[int(t * (len(chars) - 1))])
        lines.append("".join(line))
    return lines


def build_parser():
    p = argparse.ArgumentParser(
        prog="mandelbrot-ascii", description="在终端打印曼德博集合字符画（支持区域缩放）"
    )
    p.add_argument("--width", type=int, default=72, help="画布宽 10-240，默认 72")
    p.add_argument("--height", type=int, default=None,
                   help="画布高 5-160，默认自动 ≈ width*0.44")
    p.add_argument("--cx", type=float, default=-0.6, help="视野中心实部，默认 -0.6")
    p.add_argument("--cy", type=float, default=0.0, help="视野中心虚部，默认 0.0")
    p.add_argument("--scale", type=float, default=1.5, help="视野半宽 (0,10]，默认 1.5")
    p.add_argument("--max-iter", type=int, default=150, help="最大迭代数 >=10，默认 150")
    p.add_argument("--preset", choices=sorted(PRESETS), default=None,
                   help="预设机位: " + "|".join(sorted(PRESETS)))
    p.add_argument("--chars", default=" .:-=+*#%@",
                   help="由暗到亮的字符梯度，默认 ' .:-=+*#%%@'")
    return p


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)

    if args.preset:
        cx, cy, scale = PRESETS[args.preset]
    else:
        cx, cy, scale = args.cx, args.cy, args.scale
    width = args.width
    height = args.height if args.height else max(8, round(width * 0.44))

    if not (10 <= width <= 240):
        print("错误: --width 需在 10-240 之间", file=sys.stderr)
        return 2
    if not (5 <= height <= 160):
        print("错误: --height 需在 5-160 之间", file=sys.stderr)
        return 2
    if not (0 < scale <= 10):
        print("错误: --scale 需在 (0, 10] 之间", file=sys.stderr)
        return 2
    if scale < 1e-6:
        print("警告: scale 过小，float 精度不足，图像可能失真", file=sys.stderr)
    if args.max_iter < 10:
        print("错误: --max-iter 至少为 10", file=sys.stderr)
        return 2
    chars = args.chars
    if len(chars) < 2 or any(c in "\n\r\t" for c in chars):
        print("错误: --chars 至少 2 个字符且不能含换行/制表符", file=sys.stderr)
        return 2

    lines = render(cx, cy, scale, width, height, args.max_iter, chars)
    print(f"# mandelbrot center=({cx:+g},{cy:+g}) scale={scale:g}"
          f" size={width}x{height} max_iter={args.max_iter}")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
