#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""时间单位换算（duration-convert）。

用途：
    在秒、分、时、天、周、月、年之间按固定定义换算，支持「1h30m」「2d4h」
    这类单位表达式，以及数字四则运算（+ - * / // %）；纯数字按秒处理。
    相邻的单位项自动相加（1h30m = 1h + 30m）；显式乘除请写运算符。
    换算定义为固定值（非日历换算）：
        1 分 = 60 秒；1 时 = 3600 秒；1 天 = 86400 秒
        1 周 = 7 天 = 604800 秒；1 月 = 30 天 = 2592000 秒；1 年 = 365 天 = 31536000 秒

用法：
    python duration-convert.py 1h30m --to s      # 5400 秒
    python duration-convert.py 2w --all          # 输出全部单位
    python duration-convert.py "3600*2" --to h   # 表达式 → 2 时
    python duration-convert.py 90m               # 不带 --to 时默认输出全部单位
    python duration-convert.py --demo            # 内置示例自测（安全）

单位写法：s/秒、m/分、h/时/小时、d/天、w/周、mo/月、y/年
    （英文大小写不敏感；用 mo 表示月，避免与 m=分 混淆）。
    表达式求值基于 ast 白名单，不使用 eval，仅允许数字与 + - * / // %。

退出码：0 = 成功；2 = 表达式或单位不合法。
"""

from __future__ import annotations

import argparse
import ast
import operator
import re
import sys

UNITS = {
    "s": ("秒", 1.0),
    "m": ("分", 60.0),
    "h": ("时", 3600.0),
    "d": ("天", 86400.0),
    "w": ("周", 604800.0),
    "mo": ("月", 2592000.0),
    "y": ("年", 31536000.0),
}
ALIASES = {
    "s": "s", "sec": "s", "secs": "s", "second": "s", "seconds": "s", "秒": "s",
    "m": "m", "min": "m", "mins": "m", "minute": "m", "minutes": "m", "分": "m", "分钟": "m",
    "h": "h", "hr": "h", "hrs": "h", "hour": "h", "hours": "h", "时": "h", "小时": "h",
    "d": "d", "day": "d", "days": "d", "天": "d", "日": "d",
    "w": "w", "week": "w", "weeks": "w", "周": "w", "星期": "w",
    "mo": "mo", "month": "mo", "months": "mo", "月": "mo",
    "y": "y", "year": "y", "years": "y", "年": "y",
}
BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}

_ALTERNATION = "|".join(sorted((re.escape(k) for k in ALIASES), key=len, reverse=True))
_NUMBER = r"(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?"
UNIT_EXPR = re.compile(rf"({_NUMBER})\s*({_ALTERNATION})", re.IGNORECASE)


def _setup_stdio() -> None:
    """让中文输出在 Windows 各类管道下不因编码报错。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def resolve_unit(unit: str) -> str:
    key = unit if not unit.isascii() else unit.lower()
    try:
        return ALIASES[key]
    except KeyError:
        raise ValueError(f"不支持的单位: {unit!r}（可用: s/m/h/d/w/mo/y 或中文）")


def safe_eval(text: str) -> float:
    """基于 ast 白名单的四则运算求值，不使用 eval。"""
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"表达式语法错误: {text!r}（{exc.msg}）")

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in BIN_OPS:
            left, right = ev(node.left), ev(node.right)
            if type(node.op) in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
                raise ValueError("除数为 0")
            return BIN_OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = ev(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        raise ValueError(f"表达式包含不支持的语法（仅允许数字与 + - * / // %）: {text!r}")

    try:
        return float(ev(tree))
    except RecursionError:
        raise ValueError("表达式嵌套过深")


def expr_to_seconds(expr: str) -> float:
    text = expr.strip()
    if not text:
        raise ValueError("表达式为空")

    def repl(match: "re.Match") -> str:
        number, unit = match.group(1), match.group(2)
        factor = UNITS[resolve_unit(unit)][1]
        return f"({number} * {factor:.10g})"

    expanded = UNIT_EXPR.sub(repl, text)
    # 相邻两个单位项之间补“+”（如 1h30m → (3600)+(1800)）
    expanded = re.sub(r"\)(?=\s*[\d(.])", ")+", expanded)
    leftover = re.sub(r"[\s\d.()+\-*/%eE]", "", expanded)
    if leftover:
        raise ValueError(f"表达式包含无法识别的内容: {leftover[:20]!r}（原文: {expr!r}）")
    return safe_eval(expanded)


def convert(seconds: float, code: str) -> float:
    return seconds / UNITS[code][1]


def fmt_num(value: float, max_digits: int = 6) -> str:
    value = float(value)
    if abs(value) < 1e15 and value.is_integer():
        return str(int(value))
    text = f"{value:.{max_digits}f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-") else "0"


def humanize(seconds: float) -> str:
    sign = "-" if seconds < 0 else ""
    total = int(round(abs(seconds)))
    if total == 0:
        return "0秒"
    chunks = []
    for size, name in ((86400, "天"), (3600, "小时"), (60, "分"), (1, "秒")):
        if total >= size:
            count, total = divmod(total, size)
            chunks.append(f"{count}{name}")
    return sign + ("".join(chunks) or "0秒")


def main(argv=None) -> int:
    _setup_stdio()
    parser = argparse.ArgumentParser(
        prog="duration-convert",
        description="秒/分/时/天/周/月/年按定义换算，支持 1h30m 这类表达式与四则运算。",
    )
    parser.add_argument("expr", nargs="?", help="表达式，如 1h30m、2d、90m、3600*2；纯数字按秒")
    parser.add_argument("--to", dest="target", metavar="UNIT",
                        help="目标单位：s/m/h/d/w/mo/y 或中文（省略则输出全部单位）")
    parser.add_argument("--all", action="store_true",
                        help="输出全部单位（默认行为；与 --to 同用时 --to 优先）")
    parser.add_argument("--round", dest="ndigits", type=int, default=6, metavar="N",
                        help="输出小数位数上限（默认 6，多余的 0 会省略）")
    parser.add_argument("--demo", action="store_true", help="内置示例自测（安全）")
    args = parser.parse_args(argv)

    if args.demo:
        samples = ["1h30m", "2w", "90m", "3600*2+30m", "0.5y"]
        try:
            for item in samples:
                seconds = expr_to_seconds(item)
                print(f"{item!r:>14}  →  {fmt_num(seconds, args.ndigits)} 秒（{humanize(seconds)}）")
            seconds = expr_to_seconds(samples[0])
        except ValueError as exc:
            print(f"错误: {exc}", file=sys.stderr)
            return 2
        print("其中 1h30m 的全部单位：")
        for code in ("s", "m", "h", "d", "w", "mo", "y"):
            name, _ = UNITS[code]
            print(f"  {name}: {fmt_num(convert(seconds, code), args.ndigits)}")
        return 0

    if args.expr is None:
        parser.error("请提供表达式（位置参数）或使用 --demo")

    try:
        seconds = expr_to_seconds(args.expr)
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    if args.target:
        try:
            code = resolve_unit(args.target.strip())
        except ValueError as exc:
            print(f"错误: {exc}", file=sys.stderr)
            return 2
        value = convert(seconds, code)
        print(f"{args.expr}  →  {fmt_num(value, args.ndigits)} {UNITS[code][0]}"
              f"（{fmt_num(seconds, args.ndigits)} 秒）")
        return 0

    print(f"表达式: {args.expr}  →  共 {fmt_num(seconds, args.ndigits)} 秒（{humanize(seconds)}）")
    print("按定义换算（月=30天，年=365天）:")
    for code in ("s", "m", "h", "d", "w", "mo", "y"):
        name, _ = UNITS[code]
        print(f"  {name}: {fmt_num(convert(seconds, code), args.ndigits)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
