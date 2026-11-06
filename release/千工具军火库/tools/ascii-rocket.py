#!/usr/bin/env python3
"""火箭发射 (ascii-rocket) -- 倒计时后火箭升空喷焰的逐帧动画。

示例命令:
    python ascii-rocket.py                                        # 默认 T-3 倒计时 + 24 帧
    python ascii-rocket.py --countdown 5 --frames 40 --delay 0.2
    python ascii-rocket.py --countdown 1 --frames 6 --delay 0.05   # 快速预览/自测

说明:
    * 终端 (tty) 下用 ANSI 序列原地逐帧重绘; 管道/重定向时改为逐帧平铺打印,
      便于自测与记录日志。
    * Windows 会自动尝试打开终端 VT 转义支持 (无需 colorama)。
    * 单文件, 只依赖 Python 标准库; 输出强制 UTF-8。
"""

from __future__ import annotations

import argparse
import sys
import time

ROCKET = (
    "    /\\    ",
    "   /  \\   ",
    "  |    |  ",
    "  | CC |  ",
    "  |    |  ",
    " /|    |\\ ",
    "/_|____|_\\",
)

# 火焰自上而下收窄, A/B 两套字符做帧间闪烁
FLAME_A = ("  ******  ", "  ******  ", "   ****   ", "    **    ")
FLAME_B = ("  *+**+*  ", "  **+**+  ", "   +**+   ", "    ++    ")
MAX_FLAME = len(FLAME_A)
BLOCK_H = len(ROCKET) + MAX_FLAME + 1  # 火箭 + 最大火焰 + 1 行状态栏


def force_utf8() -> None:
    """Windows 管道/Git Bash 下 stdout 默认是 ANSI 代码页 (如 gbk), 统一改成 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def enable_ansi() -> None:
    """Windows 10+ 终端默认可能未开 VT 转义序列, 这里尝试打开; 其他平台为空操作。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass


def build_frame(idx: int, total: int) -> list[str]:
    """第 idx 帧: 火焰越长, 头顶留白越少 => 火箭位置越高。"""
    t = (idx + 1) / total
    rows = 1 + min(MAX_FLAME - 1, int(t * MAX_FLAME))  # 1..MAX_FLAME
    flame = (FLAME_A if idx % 2 == 0 else FLAME_B)[:rows]
    pad_top = [" " * 10] * (MAX_FLAME - rows)
    art = pad_top + list(ROCKET) + list(flame)
    bar = "#" * int(t * 20)
    alt = int(2000 * t * t)
    status = f"T+{t * 10:04.1f}s alt={alt:4d}m [{bar:<20}] {int(t * 100):3d}%"
    return art + [status]


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(
        prog="ascii-rocket.py",
        description="倒计时后火箭升空喷焰的逐帧 ASCII 动画",
    )
    parser.add_argument("--countdown", type=int, default=3, help="倒计时秒数, 0~60, 默认 3")
    parser.add_argument("--frames", type=int, default=24, help="升空帧数, 1~200, 默认 24")
    parser.add_argument("--delay", type=float, default=0.15, help="每帧间隔秒, 0.01~2.0, 默认 0.15")
    args = parser.parse_args(argv)

    if not 0 <= args.countdown <= 60:
        parser.error("--countdown 须在 0~60 之间")
    if not 1 <= args.frames <= 200:
        parser.error("--frames 须在 1~200 之间")
    if not 0.01 <= args.delay <= 2.0:
        parser.error("--delay 须在 0.01~2.0 秒之间")

    enable_ansi()
    out = sys.stdout
    tick = max(0.05, min(1.0, args.delay * 4))

    for i in range(args.countdown, 0, -1):
        print(f"        T-{i} ...")
        out.flush()
        time.sleep(tick)
    print("        点火! IGNITION!")
    out.flush()
    time.sleep(tick)

    is_tty = bool(out.isatty()) if hasattr(out, "isatty") else False

    for idx in range(args.frames):
        block = build_frame(idx, args.frames)
        if is_tty:
            if idx > 0:
                out.write(f"\x1b[{BLOCK_H}F")  # 光标移回帧首行, 原地重绘
            out.write("".join(line + "\x1b[K\n" for line in block))
        else:
            if idx > 0:
                out.write("\n")  # 平铺模式下帧间空一行
            out.write("".join(line + "\n" for line in block))
        out.flush()
        if idx < args.frames - 1:
            time.sleep(args.delay)

    print("\n>>> LIFTOFF! 火箭升空, 一路平安 <<<")
    return 0


if __name__ == "__main__":
    sys.exit(main())
