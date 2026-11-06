#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冷笑话盲盒 (joke-box)。

用途:
    每次运行从自家笑话库随机抽一条冷笑话打印出来；用 -a/--append
    可以往笑话库里追加新笑话(纯文本，一行一条)。笑话库默认在
    ~/.joke_box_jokes.txt，首次运行会自动用内置笑话初始化。

示例命令:
    python joke-box.py                       # 随机抽一条冷笑话
    python joke-box.py -a "新的冷笑话内容"     # 追加进自家笑话库
    python joke-box.py --list                # 列出库里的全部笑话
    python joke-box.py -f myjokes.txt        # 使用别的笑话库文件

只依赖 Python 标准库。
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import unicodedata

DEFAULT_LIB = os.path.join(os.path.expanduser("~"), ".joke_box_jokes.txt")
RESET = "\x1b[0m"

DEFAULT_JOKES = (
    "为什么飞机飞得那么高都不会撞到星星？因为星星会「闪」呀。",
    "一只北极熊把自己身上的毛拔光后，说了一句话：好冷啊。",
    "绿豆从五楼跳下来摔流血了，变成红豆；后来气死了，变成黄豆。",
    "什么动物最容易被贴在墙上？海豹，因为那是海报。",
    "有一天一个小包子走在路上，突然觉得饿了，就把自己吃了。",
    "橡皮、老虎、狮子谁最厉害？橡皮，因为橡皮擦(象、虎、狮都擦)。",
    "为什么海水是咸的？因为鱼儿在里面流了太多汗。",
    "世界上最勇敢的鸡是什么鸡？肯德基——敢被人炸。",
    "为什么程序员分不清万圣节和圣诞节？因为 OCT 31 == DEC 25。",
    "蚊子咬人前为什么要嗡嗡叫？因为它得先给你做个「皮试」。",
    "冷笑话为什么特别冷？因为它刚从冰箱里拿出来。",
    "为什么数学书总是很忧郁？因为它有太多的问题要解决。",
)


def setup_stdio() -> None:
    """把标准流固定成 UTF-8，避免 Windows 本地编码(如 GBK)炸出 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def paint(text: str, color: str, plain: bool) -> str:
    return text if plain else f"\x1b[{color}m{text}{RESET}"


def dw(text: str) -> int:
    """显示宽度: 全角/宽字符按 2 列计，其余按 1 列。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1 for ch in text)


def fit(text: str, width: int) -> str:
    """把 text 用空格补齐到显示宽度 width(居中)。"""
    pad = max(0, width - dw(text))
    left = pad // 2
    return " " * left + text + " " * (pad - left)


def load_jokes(path: str) -> list[str]:
    """读取笑话库；文件不存在时先用内置笑话初始化。"""
    if not os.path.exists(path):
        lib_dir = os.path.dirname(os.path.abspath(path))
        if lib_dir:
            os.makedirs(lib_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(DEFAULT_JOKES) + "\n")
        print(f"(首次运行，已用内置笑话初始化 {path})")
    with open(path, "r", encoding="utf-8-sig") as f:
        return [line.strip() for line in f if line.strip()]


def draw(jokes: list[str], plain: bool) -> None:
    joke = random.choice(jokes)
    inner = max(26, dw(joke) + 6)
    lines = [
        "╭" + "─" * inner + "╮",
        "│" + fit("🎲 冷笑话盲盒", inner) + "│",
        "│" + " " * inner + "│",
        "│" + fit(joke, inner) + "│",
        "╰" + "─" * inner + "╯",
    ]
    print(paint("\n".join(lines), "96", plain))


def main() -> int:
    setup_stdio()
    parser = argparse.ArgumentParser(
        prog="joke-box",
        description="每次抽一条冷笑话；-a 可往自家笑话库追加。",
    )
    parser.add_argument("-a", "--append", action="append", metavar="JOKE",
                        help="把一条笑话追加进笑话库(可重复使用)")
    parser.add_argument("--list", action="store_true", help="列出笑话库全部条目")
    parser.add_argument("-f", "--file", default=DEFAULT_LIB,
                        help=f"笑话库文件路径(默认 {DEFAULT_LIB})")
    parser.add_argument("--plain", action="store_true", help="纯文本输出，不用 ANSI 颜色")
    args = parser.parse_args()

    if args.append:
        jokes = load_jokes(args.file)
        added = skipped = 0
        for text in args.append:
            joke = text.strip()
            if not joke:
                continue
            if joke in jokes:
                skipped += 1
                continue
            with open(args.file, "a", encoding="utf-8") as f:
                f.write(joke + "\n")
            jokes.append(joke)
            added += 1
        print(f"已追加 {added} 条(跳过重复 {skipped} 条)，笑话库现有 {len(jokes)} 条。")
        return 0

    jokes = load_jokes(args.file)
    if not jokes:
        print("笑话库是空的，用 -a \"...\" 添加一条吧!")
        return 0
    if args.list:
        for i, joke in enumerate(jokes, 1):
            print(f"{i:>3}. {joke}")
        print(f"共 {len(jokes)} 条。")
        return 0
    draw(jokes, args.plain)
    return 0


if __name__ == "__main__":
    sys.exit(main())
