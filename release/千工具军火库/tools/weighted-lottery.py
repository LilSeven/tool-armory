#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""加权抽签筒（weighted-lottery）：按权重抽人，例如组长被抽中做分享的概率更高。

用法示例：
    python weighted-lottery.py 组长:5 张三:1 李四:1            # 抽 1 人（权重 5:1:1）
    python weighted-lottery.py -n 2 组长:5 张三:1 李四:1       # 不放回连抽 2 人
    python weighted-lottery.py -n 3 --with-replacement 组长:5 张三:1   # 放回抽 3 次
    python weighted-lottery.py --show 组长:5 张三:1 李四:1     # 只显示各人中签概率
    python weighted-lottery.py -f people.txt -n 2              # 从文件读取，每行「姓名 权重」或「姓名:权重」
    python weighted-lottery.py --seed 7 组长:5 张三:1          # 固定随机种子，结果可复现

说明：
    - 仅依赖 Python 标准库；不带权重的候选默认权重为 1；
    - 放回模式用 random.choices；不放回模式按「抽中即移出、剩余重新归一」逐轮实现；
    - 退出码：0 成功；输入/用法错误为非 0（校验错误 1，命令行用法错误 2）。
"""

from __future__ import annotations

import argparse
import math
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


def fmt_num(x: float) -> str:
    """整数权重显示为整数，其余按最短形式。"""
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def parse_entry(token: str, source: str) -> tuple[str, float]:
    """解析「姓名:权重」；不带冒号则权重为 1。权重必须为正数。"""
    token = token.strip()
    if not token:
        raise ValueError(f"{source}：候选不能为空")
    if ":" in token:
        name, _, weight_text = token.rpartition(":")
        name, weight_text = name.strip(), weight_text.strip()
        if not name or not weight_text:
            raise ValueError(f"{source}：无法解析「{token}」，应为 姓名:权重")
    else:
        name, weight_text = token, "1"
    try:
        weight = float(weight_text)
    except ValueError:
        raise ValueError(f"{source}：权重不是数字：{token}") from None
    if not math.isfinite(weight) or weight <= 0:
        raise ValueError(f"{source}：权重必须为正数：{token}")
    return name, weight


def load_entries(args: argparse.Namespace) -> list[tuple[str, float]]:
    entries: list[tuple[str, float]] = []
    if args.file:
        for lineno, raw in enumerate(read_text_file(args.file).splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            source = f"{args.file} 第 {lineno} 行"
            parts = line.split()
            if len(parts) == 1:
                entries.append(parse_entry(parts[0], source))
            elif len(parts) == 2 and ":" not in parts[0]:
                entries.append(parse_entry(f"{parts[0]}:{parts[1]}", source))
            elif len(parts) == 2:
                entries.append(parse_entry(line.replace(" ", ""), source))
            else:
                raise ValueError(f"{source}：格式应为「姓名 权重」或「姓名:权重」，读到「{line}」")
    for token in args.candidates:
        entries.append(parse_entry(token, "命令行参数"))
    if not entries:
        raise ValueError("候选名单为空：请通过参数或 -f 文件提供至少一位候选人。")
    return entries


def pick_without_replacement(entries: list[tuple[str, float]], n: int,
                             rng: random.Random) -> list[str]:
    """不放回加权抽取：每轮按剩余权重轮盘赌抽一人并移出。"""
    pool = list(entries)
    winners = []
    for _ in range(n):
        total = sum(w for _, w in pool)
        r = rng.random() * total
        acc = 0.0
        for idx, (name, weight) in enumerate(pool):
            acc += weight
            if r < acc:
                winners.append(name)
                pool.pop(idx)
                break
        else:  # 浮点误差兜底
            winners.append(pool.pop() [0])
    return winners


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weighted-lottery",
        description="加权抽签筒：按权重抽人，谁的概率大一目了然。",
    )
    parser.add_argument("candidates", nargs="*", metavar="姓名:权重",
                        help="候选与权重，如 组长:5 张三:1（不带权重默认 1）")
    parser.add_argument("-f", "--file", metavar="文件",
                        help="从文件读取候选，每行「姓名 权重」或「姓名:权重」，# 为注释")
    parser.add_argument("-n", "--count", type=int, default=1, help="抽几人（默认 1）")
    parser.add_argument("--with-replacement", action="store_true",
                        help="放回模式：同一人可能被重复抽中")
    parser.add_argument("--show", action="store_true", help="只显示概率分布，不抽签")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，结果可复现")
    return parser


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    args = build_parser().parse_args(argv)

    try:
        entries = load_entries(args)
    except (OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    total = sum(w for _, w in entries)

    if args.show:
        name_col = max(display_width(n) for n, _ in entries) + 2
        print(f"共 {len(entries)} 位候选，总权重 {fmt_num(total)}：")
        print(pad("姓名", name_col) + pad("权重", 8) + "中签概率")
        for name, weight in entries:
            print(pad(name, name_col) + pad(fmt_num(weight), 8) + f"{weight / total * 100:.2f}%")
        return 0

    if args.count < 1:
        print("错误：-n/--count 至少为 1。", file=sys.stderr)
        return 1
    if not args.with_replacement and args.count > len(entries):
        print(f"错误：不放回模式抽 {args.count} 人，但候选只有 {len(entries)} 位；"
              "可减少 -n、补充候选或改用 --with-replacement。", file=sys.stderr)
        return 1

    rng = random.Random(args.seed)
    if args.with_replacement:
        names = [n for n, _ in entries]
        weights = [w for _, w in entries]
        winners = rng.choices(names, weights=weights, k=args.count)
    else:
        winners = pick_without_replacement(entries, args.count, rng)

    if args.count == 1:
        print(f"抽中：{winners[0]}（共 {len(entries)} 位候选，总权重 {fmt_num(total)}）")
    else:
        mode = "放回" if args.with_replacement else "不放回"
        print(f"抽签结果（{mode}，共抽 {args.count} 人）：")
        for i, name in enumerate(winners, 1):
            print(f"  第 {i} 抽：{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
