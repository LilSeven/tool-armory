#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多面骰盅 —— 支持 NdM 掷骰语法(如 3d6+2), 显示每次点数明细与总和。

语法:
    表达式由若干项以 +/- 连接: 骰子项 [N]dM(N 缺省为 1, d% 等价于 d100),
    或常数项; 允许空格。例: 3d6+2, d20, 2d10+1d4-1, "4d6 + 1"。

示例:
    python dice-roller.py 3d6+2
    python dice-roller.py d20
    python dice-roller.py 2d10+1d4-1
    python dice-roller.py 6d6 --seed 42      # 固定随机种子, 便于复现
    python dice-roller.py 3d6 4d4            # 一次掷多个表达式

退出码: 0 成功; 2 参数或表达式错误。
"""

import argparse
import random
import re
import sys

DICE_RE = re.compile(r"^(\d*)[dD](%|\d+)$")
SIGN_TERM_RE = re.compile(r"([+-]?)([^+-]+)")
EXPR_RE = re.compile(r"[+-]?[^+-]+(?:[+-][^+-]+)*")
MAX_DICE = 1000
MAX_SIDES = 1000000


def _setup_stdio():
    """Windows 下把标准输出/错误切到 UTF-8, 避免中文在管道/重定向中乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


class DiceError(ValueError):
    """骰子表达式解析错误。"""


def parse_expression(expr):
    """把 '3d6+2' 解析为 [('dice',+1,3,6), ('const',+1,2)]; 出错抛 DiceError。"""
    compact = re.sub(r"\s+", "", expr)
    if not compact:
        raise DiceError("表达式为空")
    if not EXPR_RE.fullmatch(compact):
        raise DiceError("表达式格式不正确")
    terms = []
    for m in SIGN_TERM_RE.finditer(compact):
        sign = -1 if m.group(1) == "-" else 1
        body = m.group(2)
        dm = DICE_RE.match(body)
        if dm:
            count_s, sides_s = dm.groups()
            count = int(count_s) if count_s else 1
            sides = 100 if sides_s == "%" else int(sides_s)
            if count < 1:
                raise DiceError("骰子数量须≥1: {!r}".format(body))
            if count > MAX_DICE:
                raise DiceError("骰子数量过多, 上限 {}: {!r}".format(MAX_DICE, body))
            if sides < 1:
                raise DiceError("骰子面数须≥1: {!r}".format(body))
            if sides > MAX_SIDES:
                raise DiceError("骰子面数过大, 上限 {}".format(MAX_SIDES))
            terms.append(("dice", sign, count, sides))
        elif body.isdigit():
            terms.append(("const", sign, int(body)))
        else:
            raise DiceError("无法识别的项: {!r}".format(body))
    if not terms:
        raise DiceError("表达式为空")
    return terms


def roll(terms, rng):
    """掷骰, 返回 (明细行列表, 总和)。"""
    lines, total = [], 0
    for term in terms:
        if term[0] == "dice":
            _, sign, count, sides = term
            rolls = [rng.randint(1, sides) for _ in range(count)]
            subtotal = sign * sum(rolls)
            total += subtotal
            lines.append("  {}d{}: {} → {:+d}".format(
                count, sides, ", ".join(str(r) for r in rolls), subtotal))
        else:
            _, sign, value = term
            total += sign * value
            lines.append("  常数: {:+d}".format(sign * value))
    return lines, total


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="dice-roller",
        description="掷骰: 支持 NdM 语法(如 3d6+2), 显示每次点数明细与总和。")
    parser.add_argument("expr", nargs="+",
                        help="骰子表达式, 如 3d6+2 / d20 / 2d10+1d4-1")
    parser.add_argument("--seed", type=int, help="随机种子(便于复现)")
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)
    exit_code = 0
    for expr in args.expr:
        try:
            terms = parse_expression(expr)
        except DiceError as exc:
            print("错误: {!r}: {}".format(expr, exc), file=sys.stderr)
            exit_code = 2
            continue
        lines, total = roll(terms, rng)
        print("掷骰: {}".format(re.sub(r"\s+", "", expr)))
        for line in lines:
            print(line)
        print("总和: {}".format(total))
    return exit_code


if __name__ == "__main__":
    _setup_stdio()
    sys.exit(main())
