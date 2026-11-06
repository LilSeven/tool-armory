#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""终端像素画 —— 方向键在网格中移动光标、空格涂色的迷你像素画编辑器，作品可保存/读取文件。

按键说明:
    方向键 / h j k l   移动光标        空格   用当前笔刷涂色
    1-8                选择笔刷 .o*+#@=~（也可直接按笔刷字符）
    e                  擦除当前格      c      清空画布
    s                  保存到文件      q      退出（若指定 --save 则退出前自动保存）

文件格式：首行为 "宽x高"，其后每行一个字符表示画布的一行，可用任意文本编辑器修改。

示例命令:
    python pixel-editor.py --size 24x12 --save my.px   # 新建 24x12 画布，退出时存盘
    python pixel-editor.py --load my.px                # 读取已有作品继续编辑
    python pixel-editor.py --load my.px --render       # 非交互: 只打印画布内容
    python pixel-editor.py --selftest                  # 内置自检: 涂色/存/读/比对
"""

import argparse
import os
import sys

BRUSHES = ".o*+#@=~"
CURSOR_ON, CURSOR_OFF = "\x1b[7m", "\x1b[0m"


def _force_utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


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


class Editor:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.grid = [[" "] * width for _ in range(height)]
        self.cx = self.cy = 0
        self.brush = "#"
        self.msg = ""

    def move(self, dx, dy):
        self.cx = max(0, min(self.width - 1, self.cx + dx))
        self.cy = max(0, min(self.height - 1, self.cy + dy))

    def paint(self, ch=None):
        self.grid[self.cy][self.cx] = self.brush if ch is None else ch

    def erase(self):
        self.grid[self.cy][self.cx] = " "

    def clear(self):
        self.grid = [[" "] * self.width for _ in range(self.height)]
        self.msg = "画布已清空"

    def save(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("%dx%d\n" % (self.width, self.height))
            for row in self.grid:
                fh.write("".join(row) + "\n")
        self.msg = "已保存到 %s" % path

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        if not lines or "x" not in lines[0]:
            raise ValueError("像素画文件格式错误: 第一行应为 '宽x高'")
        w, h = lines[0].lower().split("x")
        ed = cls(int(w), int(h))
        for y, line in enumerate(lines[1:1 + ed.height]):
            for x, ch in enumerate(line[:ed.width]):
                ed.grid[y][x] = ch
        return ed

    def render(self, cursor=False):
        lines = ["+" + "-" * self.width + "+"]
        for y, row in enumerate(self.grid):
            cells = list(row)
            if cursor and y == self.cy:
                cells[self.cx] = CURSOR_ON + cells[self.cx] + CURSOR_OFF
            lines.append("|" + "".join(cells) + "|")
        lines.append("+" + "-" * self.width + "+")
        if self.msg:
            lines.append(self.msg)
        else:
            lines.append("光标(%d,%d) 笔刷'%s' | 方向键/hjkl移动 空格涂色 e擦除 "
                         "1-8换笔刷 c清空 s保存 q退出" % (self.cx, self.cy, self.brush))
        return "\n".join(lines)


def read_key():
    """读取一个按键并归一化: 返回 'up'/'down'/'left'/'right' 或单字符。"""
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            arrow = {"H": "up", "P": "down", "K": "left", "M": "right"}
            return arrow.get(msvcrt.getwch(), "")
        return ch
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            nxt = sys.stdin.read(1)
            if nxt == "[":
                arrow = {"A": "up", "B": "down", "C": "right", "D": "left"}
                return arrow.get(sys.stdin.read(1), "")
            return nxt
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def run_interactive(ed, save_path):
    if not sys.stdin.isatty():
        print("标准输入不是终端，无法进入交互模式；请改用 --render 或 --selftest。",
              file=sys.stderr)
        return 1
    enable_ansi()
    sys.stdout.write("\x1b[2J\x1b[H" + ed.render(cursor=True) + "\n")
    sys.stdout.flush()
    while True:
        key = read_key()
        if key in ("q", "Q", "\x03"):
            break
        if key in ("up", "k"):
            ed.move(0, -1)
        elif key in ("down", "j"):
            ed.move(0, 1)
        elif key in ("left", "h"):
            ed.move(-1, 0)
        elif key in ("right", "l"):
            ed.move(1, 0)
        elif key == " ":
            ed.paint()
        elif key in ("e", "E"):
            ed.erase()
        elif key in ("c", "C"):
            ed.clear()
        elif key in ("s", "S"):
            if save_path:
                ed.save(save_path)
            else:
                ed.msg = "未指定保存路径: 请用 --save 文件名"
        elif key in BRUSHES:
            ed.brush = key
            ed.msg = ""
        elif key.isdigit() and key != "0":
            idx = int(key) - 1
            if idx < len(BRUSHES):
                ed.brush = BRUSHES[idx]
                ed.msg = "笔刷切换为 '%s'" % ed.brush
        else:
            ed.msg = ""
        sys.stdout.write("\x1b[H" + ed.render(cursor=True) + "\n")
        sys.stdout.flush()
    if save_path:
        ed.save(save_path)
        print(ed.msg)
    return 0


def selftest():
    import tempfile
    ed = Editor(12, 6)
    ed.move(3, 2)
    ed.paint()                          # (3,2) 涂 '#'
    ed.brush = "o"
    ed.move(1, 0)
    ed.paint()                          # (4,2) 涂 'o'
    assert ed.grid[2][3] == "#" and ed.grid[2][4] == "o", "涂色失败"
    ed.move(-10, -10)                   # 越界移动应停在左上角
    assert (ed.cx, ed.cy) == (0, 0), "左边界移动失败"
    ed.move(99, 99)                     # 越界移动应停在右下角
    assert (ed.cx, ed.cy) == (11, 5), "右边界移动失败"
    ed.paint()
    assert ed.grid[5][11] == "o", "右下角涂色失败"
    ed.erase()
    assert ed.grid[5][11] == " ", "擦除失败"
    ed.clear()
    assert all(ch == " " for row in ed.grid for ch in row), "清空失败"
    path = os.path.join(tempfile.gettempdir(), "pixel-editor-selftest.px")
    ed.move(2, 1)
    ed.paint()
    ed.save(path)
    back = Editor.load(path)
    assert back.grid == ed.grid and (back.width, back.height) == (12, 6), "保存/读取不一致"
    art = back.render()
    assert art.splitlines()[0].startswith("+") and "|" in art, "渲染失败"
    os.remove(path)
    print("selftest OK: 涂色/擦除/清空/边界移动/保存/读取/渲染 全部通过")
    return 0


def main(argv=None):
    _force_utf8()
    ap = argparse.ArgumentParser(description="终端像素画编辑器（方向键涂色，可存取文件）")
    ap.add_argument("--size", default="24x12", metavar="WxH",
                    help="画布尺寸，如 24x12（默认）")
    ap.add_argument("--load", metavar="FILE", help="从文件读取像素画")
    ap.add_argument("--save", metavar="FILE",
                    help="保存路径（s 键保存；若指定则退出时自动保存）")
    ap.add_argument("--render", action="store_true", help="非交互: 打印画布后退出")
    ap.add_argument("--selftest", action="store_true", help="运行内置自检")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    if args.load:
        try:
            ed = Editor.load(args.load)
        except (OSError, ValueError) as exc:
            print("读取失败: %s" % exc, file=sys.stderr)
            return 1
    else:
        try:
            w, h = (int(p) for p in args.size.lower().split("x"))
            if w < 1 or h < 1:
                raise ValueError
            ed = Editor(w, h)
        except ValueError:
            ap.error("--size 格式应为 宽x高 且为正整数，例如 24x12")

    if args.render:
        print(ed.render())
        return 0
    return run_interactive(ed, args.save)


if __name__ == "__main__":
    sys.exit(main())
