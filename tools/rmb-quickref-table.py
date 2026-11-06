#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rmb-quickref-table —— 金额大写速查表生成（Markdown 或 CSV，供打印）。

用途：
    生成一张可打印的人民币大写速查表：
      一、0–9 数字对照（零壹贰叁肆伍陆柒捌玖）
      二、数位单位（拾佰仟万亿）及示例
      三、常见整金额对照（含 105/1005 等补「零」示例）
      四、（可选）命令行追加的自定义金额
    输出 Markdown（--format md，默认）或 CSV（--format csv，utf-8-sig，
    便于 Excel 直接打开）；--out 写入文件，缺省打印到标准输出。
    大写风格：元/角/分；到「元」为止末尾加「整」，角后不加整，有分不加。

示例命令：
    python -I rmb-quickref-table.py --format md
    python -I rmb-quickref-table.py --format csv > quickref.csv
    python -I rmb-quickref-table.py --format md --out quickref.md 1234.56 0.05

输入格式：
    追加的自定义金额支持 1234.56、1,234.56、￥500、-12.34 等；
    小数最多两位，超出两位按错误处理（退出码 2）。
"""

import argparse
import csv
import re
import sys

DIGITS = "零壹贰叁肆伍陆柒捌玖"
SECTIONS = ("", "拾", "佰", "仟")
GROUPS = ("", "万", "亿", "万亿")
YUAN, JIAO, FEN = "元", "角", "分"
ZERO, WHOLE = "零", "整"

CURRENCY_PREFIXES = ("NT$", "NTD", "TWD", "CNY", "RMB", "HKD", "￥", "¥", "$")

UNIT_DEFS = (
    ("拾", 10),
    ("佰", 100),
    ("仟", 1000),
    ("万", 10 ** 4),
    ("亿", 10 ** 8),
    ("万亿", 10 ** 12),
)
COMMON_AMOUNTS = (
    "0", "0.01", "0.05", "0.1", "0.5", "1", "2", "5", "10", "15", "20", "50",
    "100", "105", "110", "150", "200", "500", "1000", "1005", "2000", "5000",
    "10000", "100000", "1000000", "10000000", "100000000",
)


class AmountError(ValueError):
    """金额无法解析或超出表示范围。"""


def parse_amount(text):
    """解析金额字符串 -> (是否负数, 元整数, 角, 分)。"""
    t = str(text).strip()
    for ch in (",", "，", " ", "\u00a0", "\t"):
        t = t.replace(ch, "")
    negative = False
    while True:
        if t.startswith("-"):
            negative = not negative
            t = t[1:]
            continue
        if t.startswith("+"):
            t = t[1:]
            continue
        hit = False
        for p in CURRENCY_PREFIXES:
            if t.startswith(p):
                t = t[len(p):]
                hit = True
                break
        if hit:
            continue
        break
    if not re.fullmatch(r"\d+(\.\d{1,2})?", t):
        raise AmountError(
            f"无法识别的金额 {text!r}：请用 1234.56 / 1,234.56 这类格式，小数最多两位"
        )
    int_s, _, frac_s = t.partition(".")
    frac = (frac_s + "00")[:2]
    return negative, int(int_s), int(frac[0]), int(frac[1])


def group_to_cn(g):
    """1..9999 的四位组转大写：5005 -> 伍仟零伍。"""
    parts = []
    pending_zero = False
    for idx in (3, 2, 1, 0):
        d = (g // 10 ** idx) % 10
        if d == 0:
            if parts:
                pending_zero = True
            continue
        if parts and pending_zero:
            parts.append(ZERO)
        pending_zero = False
        parts.append(DIGITS[d] + SECTIONS[idx])
    return "".join(parts)


def int_to_cn(n):
    """0..10^16-1 的整数转大写：100010001 -> 壹亿零壹万零壹。"""
    if n == 0:
        return ZERO
    if n >= 10 ** 16:
        raise AmountError("整数部分达到或超过 1亿亿（10^16），超出本工具表示范围")
    groups = []
    while n:
        groups.append(n % 10000)
        n //= 10000
    parts = []
    pending_zero = False
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if g == 0:
            pending_zero = True
            continue
        if parts and (pending_zero or g < 1000):
            parts.append(ZERO)
        pending_zero = False
        parts.append(group_to_cn(g) + GROUPS[i])
    return "".join(parts)


def to_upper(text):
    """金额字符串 -> 人民币大写（元/角/分，到元加整，角后不加整）。"""
    negative, yuan, jiao, fen = parse_amount(text)
    pieces = []
    if negative:
        pieces.append("负")
    if yuan == 0 and (jiao or fen):
        pieces.append(ZERO + YUAN)
    else:
        pieces.append(int_to_cn(yuan) + YUAN)
    if jiao and fen:
        pieces.append(DIGITS[jiao] + JIAO + DIGITS[fen] + FEN)
    elif jiao:
        pieces.append(DIGITS[jiao] + JIAO)
    elif fen:
        pieces.append(ZERO + DIGITS[fen] + FEN)
    else:
        pieces.append(WHOLE)
    return "".join(pieces)


def collect_rows(extra_amounts):
    """返回 (数字行, 单位行, 常用金额行, 自定义行)。"""
    digit_rows = [(str(d), DIGITS[d]) for d in range(10)]
    unit_rows = [(name, mult, to_upper(str(mult))) for name, mult in UNIT_DEFS]
    common_rows = [(amt, to_upper(amt)) for amt in COMMON_AMOUNTS]
    extra_rows = [(amt, to_upper(amt)) for amt in extra_amounts]
    return digit_rows, unit_rows, common_rows, extra_rows


def render_md(digit_rows, unit_rows, common_rows, extra_rows):
    out = [
        "# 金额大写速查表（人民币）",
        "",
        "数字：零壹贰叁肆伍陆柒捌玖；单位：拾佰仟万亿。",
        "到「元」为止末尾加「整」；角后不加整；有分不加。",
        "",
        "## 一、数字对照（0–9）",
        "",
        "| 阿拉伯数字 | 中文大写 |",
        "|---|---|",
    ]
    out += [f"| {a} | {b} |" for a, b in digit_rows]
    out += ["", "## 二、数位单位", "", "| 单位（倍数） | 示例金额 | 大写 |", "|---|---|---|"]
    out += [f"| {name}（×{mult:,}） | {mult:,} | {up} |" for name, mult, up in unit_rows]
    out += ["", "## 三、常见整金额对照", "", "| 金额（元） | 大写 |", "|---|---|"]
    out += [f"| {a} | {b} |" for a, b in common_rows]
    if extra_rows:
        out += ["", "## 四、自定义金额", "", "| 金额（元） | 大写 |", "|---|---|"]
        out += [f"| {a} | {b} |" for a, b in extra_rows]
    out += ["", "---", "由 rmb-quickref-table.py 生成（仅用 Python 标准库）"]
    return "\n".join(out) + "\n"


def render_csv_rows(digit_rows, unit_rows, common_rows, extra_rows):
    rows = [("表", "项目", "大写")]
    rows += [("数字", a, b) for a, b in digit_rows]
    rows += [("单位", f"{name}（×{mult:,}）", up) for name, mult, up in unit_rows]
    rows += [("常用金额", a, b) for a, b in common_rows]
    rows += [("自定义", a, b) for a, b in extra_rows]
    return rows


def _utf8_stdout():
    """Windows 管道/控制台下尽量用 UTF-8 输出，避免中文乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="rmb-quickref-table.py",
        description="生成 0–9、单位与常见整金额的大写速查表，输出 Markdown 或 CSV。",
    )
    parser.add_argument("amounts", nargs="*", metavar="金额",
                        help="可选：追加到「自定义金额」表的金额，如 1234.56")
    parser.add_argument("--format", choices=("md", "csv"), default="md",
                        help="输出格式（默认 md）")
    parser.add_argument("--out", metavar="文件", help="写入文件（缺省打印到标准输出）")
    args = parser.parse_args(argv)
    _utf8_stdout()
    try:
        digit_rows, unit_rows, common_rows, extra_rows = collect_rows(args.amounts)
    except AmountError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    if args.format == "md":
        text = render_md(digit_rows, unit_rows, common_rows, extra_rows)
        if args.out:
            with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
                f.write(text)
            print(f"已写入 {args.out}（Markdown）")
        else:
            sys.stdout.write(text)
    else:
        data = render_csv_rows(digit_rows, unit_rows, common_rows, extra_rows)
        if args.out:
            with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerows(data)
            print(f"已写入 {args.out}（CSV，共 {len(data)} 行含表头）")
        else:
            csv.writer(sys.stdout, lineterminator="\n").writerows(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
