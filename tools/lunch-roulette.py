#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""今日吃啥（lunch-roulette）：内置/自定义餐厅清单，滚动动画停下后宣布你命定的那家。

用法示例：
    python lunch-roulette.py                            # 内置清单 + 滚动动画
    python lunch-roulette.py --no-anim                  # 跳过动画直接揭晓
    python lunch-roulette.py 兰州拉面 沙县小吃 麦当劳     # 自定义候选餐厅
    python lunch-roulette.py -f restaurants.txt         # 从文件读取，每行一家（# 为注释）
    python lunch-roulette.py --seed 42 --no-anim        # 固定随机种子，结果可复现

说明：
    - 仅依赖 Python 标准库；
    - 输出被重定向（非终端）时默认跳过动画，可用 --anim 强制播放，方便脚本化调用；
    - 退出码：0 成功；输入/用法错误为非 0（校验错误 1，命令行用法错误 2）。
"""

from __future__ import annotations

import argparse
import random
import sys
import time

BUILTIN_RESTAURANTS = [
    "兰州拉面", "沙县小吃", "黄焖鸡米饭", "重庆小面", "过桥米线",
    "麦当劳", "肯德基", "必胜客", "东北饺子馆", "麻辣烫",
    "韩式石锅拌饭", "日式寿司", "公司食堂", "轻食沙拉", "便利店饭团",
]


def setup_stdio() -> None:
    """统一按 UTF-8 输出，避免 Windows 终端/重定向场景下的乱码或编码报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def read_text_file(path: str) -> str:
    """读取文本文件，依次尝试 utf-8(-sig) / gbk 编码，失败则抛 ValueError。"""
    last_err: Exception | None = None
    for enc in ("utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except UnicodeDecodeError as exc:
            last_err = exc
    raise ValueError(f"无法解码文件（已尝试 utf-8/gbk）：{last_err}")


def load_candidates(path: str) -> list[str]:
    """从文件读取候选餐厅：每行一家，# 开头为注释，忽略空行。"""
    items = []
    for raw in read_text_file(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        items.append(line)
    return items


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lunch-roulette",
        description="今日吃啥：滚动转盘停下后，宣布你命定的那家餐厅。",
    )
    parser.add_argument("restaurants", nargs="*", metavar="餐厅",
                        help="候选餐厅列表（不给则使用内置清单）")
    parser.add_argument("-f", "--file", metavar="文件",
                        help="从文件读取候选餐厅，每行一家，# 开头为注释")
    parser.add_argument("--no-anim", action="store_true", help="跳过滚动动画")
    parser.add_argument("--anim", action="store_true",
                        help="强制播放动画（默认仅在终端输出时播放）")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，结果可复现")
    return parser


def spin(rng: random.Random, candidates: list[str], winner: str) -> None:
    """播放滚动动画：随机闪现若干帧，最后一帧定格在 winner 上。"""
    frames, delay, factor = 20, 0.01, 1.22
    for i in range(frames):
        shown = winner if i == frames - 1 else rng.choice(candidates)
        print(f"\r  >>> {shown} <<<", end="", flush=True)
        time.sleep(delay)
        delay *= factor
    print("\r" + " " * 48 + "\r", end="")


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    args = build_parser().parse_args(argv)

    candidates: list[str] = []
    if args.file:
        try:
            candidates.extend(load_candidates(args.file))
        except (OSError, ValueError) as exc:
            print(f"错误：无法读取候选文件 {args.file}：{exc}", file=sys.stderr)
            return 1
    if args.restaurants:
        candidates.extend(args.restaurants)
    if not candidates:
        candidates = list(BUILTIN_RESTAURANTS)

    candidates = list(dict.fromkeys(n.strip() for n in candidates if n.strip()))
    if not candidates:
        print("错误：候选餐厅清单为空。", file=sys.stderr)
        return 1

    print(f"本轮候选共 {len(candidates)} 家：{'、'.join(candidates)}")

    rng = random.Random(args.seed)
    winner = rng.choice(candidates)

    animate = args.anim or (not args.no_anim and sys.stdout.isatty())
    if animate:
        print("转盘转动中，听天由命……")
        spin(rng, candidates, winner)
    print(f"★ 今日吃啥？就吃【{winner}】！祝用餐愉快。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
