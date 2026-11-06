#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""罗马数字互转 (roman-convert)

在阿拉伯数字 (1-3999) 与罗马数字之间双向转换，并校验合法性。
罗马数字输入不区分大小写，会先做严格合法性校验（重复次数、减法组合等），
非法形式如 IIIV、VV、IL 会被拒绝。

用法:
  python roman-convert.py 2024          # 阿拉伯 -> 罗马: MMXXIV
  python roman-convert.py mmxxiv        # 罗马 -> 阿拉伯: 2024
  python roman-convert.py --check IIIV  # 仅校验合法性

示例:
  python roman-convert.py 3549   -> MMMDXLIX
  python roman-convert.py MCMXCIV -> 1994
"""
import argparse
import re
import sys

ROMAN_VALUES = [("M", 1000), ("CM", 900), ("D", 500), ("CD", 400),
                ("C", 100), ("XC", 90), ("L", 50), ("XL", 40),
                ("X", 10), ("IX", 9), ("V", 5), ("IV", 4), ("I", 1)]

VALID_RE = re.compile(
    r"^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")


def to_roman(n: int) -> str:
    if not 1 <= n <= 3999:
        raise ValueError(f"超出范围 1-3999: {n}")
    out = []
    for sym, val in ROMAN_VALUES:
        while n >= val:
            out.append(sym)
            n -= val
    return "".join(out)


def from_roman(s: str) -> int:
    t = s.upper().strip()
    if not t or not VALID_RE.match(t):
        raise ValueError(f"非法罗马数字: {s!r}")
    total = 0
    i = 0
    while i < len(t):
        for sym, val in ROMAN_VALUES:
            if t.startswith(sym, i):
                total += val
                i += len(sym)
                break
        else:
            raise ValueError(f"非法罗马数字: {s!r}")
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description="阿拉伯数字与罗马数字双向转换")
    ap.add_argument("value", help="阿拉伯数字 (1-3999) 或罗马数字")
    ap.add_argument("--check", action="store_true", help="仅校验罗马数字合法性")
    args = ap.parse_args()

    v = args.value.strip()
    if args.check:
        try:
            from_roman(v)
            print(f"合法: {v.upper()}")
            return 0
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 1

    if v.isdigit():
        try:
            print(to_roman(int(v)))
        except ValueError as e:
            print(f"错误: {e}", file=sys.stderr)
            return 1
    else:
        try:
            print(from_roman(v))
        except ValueError as e:
            print(f"错误: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
