#!/usr/bin/env python3
"""命运卡牌（chance-card）——大富翁风格命运/机会卡抽取，支持自定义卡组文件。

用途：团建暖场抽卡、桌游补件、课堂互动、直播抽任务。

示例命令：
  python chance-card.py                        # 从内置卡组随机抽 1 张
  python chance-card.py -n 3                   # 连抽 3 张（同轮不重复）
  python chance-card.py --deck my_cards.txt    # 用自定义卡组抽卡
  python chance-card.py --deck my_cards.txt --list   # 只列出卡组全部卡面
  python chance-card.py --seed 7               # 固定随机种子，结果可复现

自定义卡组文件格式（utf-8 或 gbk 自动识别）：
  - 每行一张卡，空行与 # 开头的注释行忽略；
  - 可用「命运|卡面内容」或「机会|卡面内容」指定卡面类型，缺省按「机会」处理。

退出码：0 成功；1 卡组为空；2 参数错误（卡组文件不存在、连抽数超过卡组张数等）。
仅依赖 Python 标准库。
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

BUILTIN_DECK = [
    ("命运", "今天是你的生日，每位玩家送你 10 元。"),
    ("命运", "银行发放年终红利，收取股息 50 元。"),
    ("命运", "前进到起点，领取工资 200 元。"),
    ("命运", "你的存款利息到账，收取 25 元。"),
    ("命运", "获选社区模范住户，奖励 100 元。"),
    ("命运", "银行计算错误对你有利，收取 200 元。"),
    ("命运", "出售旧物得款 45 元，落袋为安。"),
    ("命运", "祖母寄来压岁钱，收取 100 元。"),
    ("机会", "超速行驶，罚款 15 元。"),
    ("机会", "立即入狱！不得经过起点，直到掷出双数才能获释。"),
    ("机会", "出狱许可证：保留此卡备用，转卖可得 50 元。"),
    ("机会", "前进到最近的铁路，并支付双倍车费。"),
    ("机会", "后退 3 格。"),
    ("机会", "缴纳房屋维修费：每栋房屋 25 元，每家旅馆 100 元。"),
    ("机会", "你当选董事会主席，向每位玩家支付 50 元。"),
    ("机会", "投资理财亏了，支付 150 元。"),
]


def _utf8_stdio() -> None:
    """Windows 控制台/管道下强制 UTF-8 输出，避免中文乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _read_text(src: str) -> str:
    """读入文本，依次尝试 utf-8 / gbk 解码。"""
    data = Path(src).read_bytes()
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _display_width(s: str) -> int:
    """近似终端显示宽度：中日韩全角字符按 2 列计，其余按 1 列。"""
    w = 0
    for ch in s:
        o = ord(ch)
        wide = (0x1100 <= o <= 0x115F or 0x2E80 <= o <= 0xA4CF
                or 0xAC00 <= o <= 0xD7A3 or 0xF900 <= o <= 0xFAFF
                or 0xFE30 <= o <= 0xFE4F or 0xFF00 <= o <= 0xFF60
                or 0xFFE0 <= o <= 0xFFE6)
        w += 2 if wide else 1
    return w


def _pad(s: str, width: int) -> str:
    """按显示宽度右侧补空格，保证中文混排时边框对齐。"""
    return s + " " * max(0, width - _display_width(s))


def _load_deck(path: Path) -> list[tuple[str, str]]:
    """解析自定义卡组文件：每行一卡，支持「命运|内容」「机会|内容」前缀。"""
    cards: list[tuple[str, str]] = []
    for raw in _read_text(str(path)).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            tag, _, text = line.partition("|")
            tag, text = tag.strip(), text.strip()
            if tag in ("命运", "机会") and text:
                cards.append((tag, text))
                continue
        cards.append(("机会", line))
    return cards


def _render(idx: int, total: int, tag: str, text: str) -> str:
    """渲染一张带边框的卡面。"""
    header = f"{tag}卡 · 第 {idx}/{total} 张"
    w = max(_display_width(header), _display_width(text))
    return "\n".join([
        "┌" + "─" * (w + 2) + "┐",
        "│ " + _pad(header, w) + " │",
        "│ " + _pad(text, w) + " │",
        "└" + "─" * (w + 2) + "┘",
    ])


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="chance-card",
        description="大富翁风格命运/机会卡抽取，可用 --deck 换自定义卡组。",
    )
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="连抽张数（默认 1，同轮不重复）")
    parser.add_argument("--deck", default=None, metavar="FILE",
                        help="自定义卡组文件（格式见模块 docstring）")
    parser.add_argument("--list", action="store_true",
                        help="列出卡组全部卡面后退出，不抽卡")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子（相同种子结果可复现）")
    args = parser.parse_args(argv)

    if args.deck:
        deck_path = Path(args.deck)
        if not deck_path.is_file():
            print(f"错误：找不到卡组文件 {args.deck}", file=sys.stderr)
            return 2
        deck = _load_deck(deck_path)
        deck_name = str(deck_path)
    else:
        deck = list(BUILTIN_DECK)
        deck_name = "内置卡组"

    if args.list:
        print(f"卡组 {deck_name}：共 {len(deck)} 张")
        for i, (tag, text) in enumerate(deck, 1):
            print(f"  {i:>2}. [{tag}] {text}")
        return 0

    if not deck:
        print("错误：卡组为空，无卡可抽。", file=sys.stderr)
        return 1
    if args.count < 1:
        print("错误：-n/--count 必须 ≥ 1。", file=sys.stderr)
        return 2
    if args.count > len(deck):
        print(f"错误：卡组只有 {len(deck)} 张，不够连抽 {args.count} 张。",
              file=sys.stderr)
        return 2

    picked = random.Random(args.seed).sample(deck, args.count)
    for i, (tag, text) in enumerate(picked, 1):
        print(_render(i, args.count, tag, text))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
