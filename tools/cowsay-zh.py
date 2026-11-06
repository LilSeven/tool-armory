#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cowsay-zh（中文 cowsay）—— 小牛/小猫等动物气泡说话，完整支持中文。

按东亚全角宽度计算对齐，中文不会把气泡撑歪；不加 --animal 时每次随机
挑一只动物；消息可来自命令行参数，也可以从管道 stdin 读入。

示例:
    python cowsay-zh.py 你好，世界
    python cowsay-zh.py --animal cat 我是一只小猫咪
    echo "来自管道的中文消息" | python cowsay-zh.py
    python cowsay-zh.py -a penguin -w 30 很长很长的一段话会按宽度自动折行
    python cowsay-zh.py --list                        # 查看可用动物

退出码: 0 成功；2 参数错误（无消息等）。
"""

import argparse
import random
import sys
import unicodedata

# 每种动物是气泡下方的一组 ASCII 画（不随消息变化）
ANIMALS = {
    "cow": [
        "        \\   ^__^",
        "         \\  (oo)\\_______",
        "            (__)\\       )\\/\\",
        "                ||----w |",
        "                ||     ||",
    ],
    "cat": [
        "         \\    /\\_/\\",
        "          \\   ( o.o )",
        "             > ^ <",
    ],
    "penguin": [
        "         \\   .--.",
        "          \\ |o_o |",
        "            |:_/ |",
        "           //   \\ \\",
        "          (|     | )",
        "         /'\\_   _/'\\",
        "         \\___)=(___/",
    ],
    "rabbit": [
        "         \\   (\\(\\",
        "          \\  ( -.-)",
        '             o_(")(")',
    ],
}


def force_utf8_stdio():
    """输出流编码非 UTF-8 时（如 Windows 管道默认 GBK）切到 UTF-8，避免乱码或报错。"""
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
            if enc and enc != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def disp_width(s):
    """按终端显示宽度计宽：全角字符（F/W）算 2 列，其余算 1 列。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("F", "W") else 1 for c in s)


def pad(s, width):
    """把字符串按显示宽度左对齐补空格到 width 列。"""
    return s + " " * max(0, width - disp_width(s))


def hard_chunks(word, width):
    """把超宽的词（如无空格的中文长句）按显示宽度硬切成若干段。"""
    if disp_width(word) <= width:
        return [word]
    chunks, cur, curw = [], "", 0
    for ch in word:
        cw = disp_width(ch)
        if cur and curw + cw > width:
            chunks.append(cur)
            cur, curw = "", 0
        cur += ch
        curw += cw
    if cur:
        chunks.append(cur)
    return chunks


def wrap_text(text, width):
    """按显示宽度贪心折行：优先在空格处断开，放不下再硬切。"""
    out = []
    for raw in (text.splitlines() or [""]):
        cur, curw = "", 0
        for wi, word in enumerate(raw.split(" ")):
            pieces = hard_chunks(word, width)
            for pi, piece in enumerate(pieces):
                pw = disp_width(piece)
                if pi > 0:  # 同一个词硬切出来的后续段：紧跟排，放不下就换行
                    if curw + pw <= width:
                        cur += piece
                        curw += pw
                    else:
                        out.append(cur)
                        cur, curw = piece, pw
                elif curw == 0:
                    cur, curw = piece, pw
                elif curw + 1 + pw <= width:
                    cur += " " + piece
                    curw += 1 + pw
                else:
                    out.append(cur)
                    cur, curw = piece, pw
        out.append(cur)
    return out


def bubble(lines):
    """把已折行的文本画成 cowsay 气泡（顶 _ 底 -，单行 <>，多行 //||\\）。"""
    w = max(disp_width(l) for l in lines)
    top = " " + "_" * (w + 2)
    bottom = " " + "-" * (w + 2)
    if len(lines) == 1:
        body = ["< " + lines[0] + " >"]
    else:
        body = ["/ " + pad(lines[0], w) + " \\"]
        for mid in lines[1:-1]:
            body.append("| " + pad(mid, w) + " |")
        body.append("\\ " + pad(lines[-1], w) + " /")
    return [top] + body + [bottom]


def render(text, animal, width):
    return "\n".join(bubble(wrap_text(text, width)) + ANIMALS[animal])


def build_parser():
    p = argparse.ArgumentParser(
        prog="cowsay-zh",
        description="动物气泡说话，支持中文全角对齐（cowsay 克隆）。",
    )
    p.add_argument("message", nargs="*",
                   help="要说的消息；省略且 stdin 非终端时从 stdin 读取")
    p.add_argument("-a", "--animal", choices=sorted(ANIMALS), default=None,
                   help="动物种类（默认每次随机）")
    p.add_argument("-w", "--width", type=int, default=40,
                   help="气泡内文最大显示宽度（默认 40）")
    p.add_argument("--seed", type=int, default=None, help="随机选动物时的种子")
    p.add_argument("-l", "--list", action="store_true", help="列出可用动物后退出")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    force_utf8_stdio()
    if args.list:
        print("可用动物: " + ", ".join(sorted(ANIMALS)))
        return 0
    if args.width < 4:
        print("错误：--width 至少为 4。", file=sys.stderr)
        return 2
    if args.message:
        text = " ".join(args.message)
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        print("错误：请在命令行给出消息，或用管道传入。", file=sys.stderr)
        build_parser().print_usage(sys.stderr)
        return 2
    text = text.strip() or "……"
    if args.animal is not None:
        animal = args.animal
    else:
        rng = random.Random(args.seed) if args.seed is not None else random.SystemRandom()
        animal = rng.choice(sorted(ANIMALS))
    print(render(text, animal, args.width))
    return 0


if __name__ == "__main__":
    sys.exit(main())
