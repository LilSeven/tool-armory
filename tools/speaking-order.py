#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抽签排顺序（speaking-order）：为汇报/演讲随机生成出场顺序，并打印签号对照表。

用法示例：
    python speaking-order.py 张三 李四 王五 赵六         # 随机出场顺序 + 签号对照表
    python speaking-order.py -f names.txt               # 从文件读取（每行一人，# 注释）
    python speaking-order.py -o order.txt 张三 李四     # 结果同时写入文本文件
    python speaking-order.py --seed 42 张三 李四        # 固定随机种子，结果可复现

说明：
    - 仅依赖 Python 标准库；每人随机领一个互不重复的签号，签号从小到大即出场顺序；
    - 对照表按抽签前的名单顺序排列，方便对号入座；
    - 退出码：0 成功；输入/用法错误为非 0（校验错误 1，命令行用法错误 2）。
"""

from __future__ import annotations

import argparse
import random
import sys
import unicodedata


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


def display_width(text: str) -> int:
    """按终端显示宽度计算（中文等全角字符按 2 列计）。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def pad(text: str, width: int) -> str:
    """按显示宽度右侧补空格，用于对齐表格。"""
    return text + " " * max(0, width - display_width(text))


def load_names(args: argparse.Namespace) -> list[str]:
    """合并文件名单与命令行名单；检查重复与空白。"""
    names: list[str] = []
    if args.file:
        for raw in read_text_file(args.file).splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            names.append(line)
    names.extend(args.people)
    names = [n.strip() for n in names if n.strip()]
    seen: set[str] = set()
    for n in names:
        if n in seen:
            raise ValueError(f"名单里有重复的名字：{n}")
        seen.add(n)
    return names


def build_report(names: list[str], lots: list[int]) -> str:
    """lots 与 names 一一对应（1..N 互不重复），生成签号对照表文本。"""
    order = sorted(range(len(names)), key=lambda i: lots[i])
    name_col = max(display_width(n) for n in names) + 2
    lot_col = 8
    bar = "-" * (name_col + lot_col + 12)
    lines = [
        f"出场顺序抽签结果（共 {len(names)} 人）",
        bar,
        pad("姓名", name_col) + pad("签号", lot_col) + "出场顺序",
    ]
    for i, name in enumerate(names):
        pos = order.index(i) + 1
        lines.append(pad(name, name_col) + pad(f"{lots[i]:02d}", lot_col) + f"第 {pos} 位")
    lines.append(bar)
    lines.append("出场顺序：" + " → ".join(names[j] for j in order))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="speaking-order",
        description="抽签排顺序：随机决定汇报/演讲的出场顺序，并打印签号对照表。",
    )
    parser.add_argument("people", nargs="*", metavar="名字", help="参与名单（至少 2 人，不得重复）")
    parser.add_argument("-f", "--file", metavar="文件", help="从文件读取名单，每行一人，# 为注释")
    parser.add_argument("-o", "--output", metavar="文件", help="把结果同时写入文本文件（UTF-8）")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，结果可复现")
    return parser


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    args = build_parser().parse_args(argv)

    try:
        names = load_names(args)
        if len(names) < 2:
            raise ValueError(f"至少需要 2 人才能排顺序，现在只有 {len(names)} 人。")
        rng = random.Random(args.seed)
        lots = rng.sample(range(1, len(names) + 1), len(names))
        report = build_report(names, lots)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(report + "\n")
    except (OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print(report)
    if args.output:
        print(f"结果已写入：{args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
