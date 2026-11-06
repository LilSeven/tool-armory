#!/usr/bin/env python3
"""科拿米秘技彩蛋 —— 监听「上上下下左右左右BA」(Konami Code) 触发彩蛋的演示脚本。

用途:
    逐个记录输入的按键; 当最近的按键序列恰好组成经典秘技
    上 上 下 下 左 右 左 右 B A 时, 打印彩蛋画面与 “+30 LIVES”。
    提供两种模式:
      * 交互模式: 不带参数且标准输入是终端时, 直接监听真实键盘
        (Windows 用 msvcrt, POSIX 用 termios; Esc 或 Ctrl+C 退出);
      * 模拟模式: 用 --keys 参数或 --stdin 管道喂入按键名, 便于脚本化自测。

按键名写法(模拟模式, 不区分大小写):
    上 = up / u / w / ↑        下 = down / d / s / ↓
    左 = left / l / ←          右 = right / r / →
    按钮 = b / a
    注意: 字母 a 是 “A 按钮”, 不表示左方向; 左方向请用 l 或 left。

示例命令:
    python konami-egg.py                                 # 交互监听(需要终端 tty)
    python konami-egg.py --keys "u u d d l r l r b a"    # 命令行模拟, 命中彩蛋
    python konami-egg.py --keys "u d b a"                # 未命中, 正常退出
    printf 'up up down down left right left right b a\\n' | python konami-egg.py --stdin

退出码: 0 = 正常结束(无论是否命中彩蛋); 2 = 参数错误。
"""

import argparse
import sys
from collections import deque

TARGET = ["up", "up", "down", "down", "left", "right", "left", "right", "b", "a"]

ALIASES = {
    "up": "up", "u": "up", "w": "up", "↑": "up",
    "down": "down", "dn": "down", "d": "down", "s": "down", "↓": "down",
    "left": "left", "l": "left", "←": "left",
    "right": "right", "r": "right", "→": "right",
    "b": "b", "a": "a",
}

EGG_ART = """\
    * * * * *   ✦ 彩 蛋 触 发 ✦   * * * * *

        K  O  N  A  M  I
        ↑ ↑ ↓ ↓ ← → ← → B A

        + 30 LIVES UNLOCKED !
"""


def normalize(token):
    """把任意写法的按键名标准化; 无法识别返回 None。"""
    return ALIASES.get(str(token).strip().lower())


def progress_of(history):
    """返回 history 末尾与 TARGET 前缀的最长匹配长度。"""
    h = list(history)
    for k in range(min(len(h), len(TARGET)), 0, -1):
        if h[-k:] == TARGET[:k]:
            return k
    return 0


def tokens_from_args(keys):
    for tok in keys.replace(",", " ").split():
        yield tok


def tokens_from_stdin(stream):
    for line in stream:
        for tok in line.split():
            yield tok


def tokens_from_keyboard():
    """交互模式: 逐个产出原始按键; Esc 结束, Ctrl+C 抛 KeyboardInterrupt。"""
    if sys.platform == "win32":
        import msvcrt
        arrows = {b"H": "up", b"P": "down", b"K": "left", b"M": "right"}
        while True:
            ch = msvcrt.getch()
            if ch in (b"\x00", b"\xe0"):          # 方向键/功能键前缀
                yield arrows.get(msvcrt.getch(), "?")
            elif ch == b"\x1b":                   # Esc 退出
                return
            else:
                yield ch.decode("utf-8", "replace")
    else:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            while True:
                ch = sys.stdin.read(1)
                if ch == "\x1b":
                    if sys.stdin.read(1) == "[":
                        yield {"A": "up", "B": "down",
                               "D": "left", "C": "right"}.get(sys.stdin.read(1), "?")
                    else:
                        return
                else:
                    yield ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def consume(tokens, interactive=False):
    history = deque(maxlen=len(TARGET))
    steps = hits = 0
    if not interactive:
        print("目标序列: " + " ".join(TARGET))
    for raw in tokens:
        if raw == "\x03":                          # Ctrl+C
            raise KeyboardInterrupt
        key = normalize(raw)
        if key is None:
            if str(raw).strip():
                print("  [忽略] 未知输入 %r" % raw)
            continue
        steps += 1
        history.append(key)
        prog = progress_of(history)
        if prog == len(TARGET):
            hits += 1
            print("  输入 %-5s 进度 %d/%d  ← 完整命中!" % (key, prog, len(TARGET)))
            print(EGG_ART)
            history.clear()
        else:
            print("  输入 %-5s 进度 %d/%d" % (key, prog, len(TARGET)))
    print("共处理 %d 个有效按键, 触发彩蛋 %d 次。" % (steps, hits))
    return hits


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        if not sys.stdin.isatty():      # 管道输入按 UTF-8 读, 避免 GBK 误码
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="科拿米秘技彩蛋: 上上下下左右左右BA (演示脚本)")
    ap.add_argument("--keys", help="模拟模式: 空格或逗号分隔的按键名串")
    ap.add_argument("--stdin", action="store_true",
                    help="模拟模式: 从标准输入逐行读取按键名")
    ns = ap.parse_args(argv)

    if ns.keys is not None:
        consume(tokens_from_args(ns.keys))
        return 0
    if ns.stdin or not sys.stdin.isatty():
        consume(tokens_from_stdin(sys.stdin))
        return 0
    print("进入交互监听模式: 按 ↑↑↓↓←→←→BA 触发彩蛋; Esc / Ctrl+C 退出。")
    try:
        consume(tokens_from_keyboard(), interactive=True)
    except KeyboardInterrupt:
        print("\n[中断] 已退出, 再见!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
