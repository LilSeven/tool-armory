#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rmb-uppercase-variants —— 对同一金额输出多种人民币大写规范变体，便于对照。

用途：
    人民币大写在不同规范与地区习惯下存在取舍差异。本工具对同一金额一次性
    给出六种变体，便于出纳/开发对照选择：
      A 标准式   人民币前缀 + 补零 + 仅到「元」为止加「整」（央行示例风格：角后不加整）
      B 无前缀式 同 A 但不加「人民币」
      C 正字式   同 A 但「整」写作「正」（不少地区票据习惯）
      D 省零式   万位空档不补「零」、整数部分为零时省略「零元」（会计规范允许的简写）
      E 拾字式   「壹拾」写作「拾」（老式写法；票据防篡改规范要求壹拾）
      F 角后加整式 「角」后也写「整」（银行实务常见）
    某差异项在该金额下不生效时，对应行会与标准式同形，对照即知。

示例命令：
    python -I rmb-uppercase-variants.py 1234.56
    python -I rmb-uppercase-variants.py 100.5 10 1000005 0.05

输入格式：
    支持 1234.56、1,234.56、￥1,234.56、-12.34（负数）等；
    小数最多两位，超出两位按错误处理（退出码 2）。
"""

import argparse
import re
import sys

DIGITS = "零壹贰叁肆伍陆柒捌玖"
SECTIONS = ("", "拾", "佰", "仟")
GROUPS = ("", "万", "亿", "万亿")
YUAN, JIAO, FEN = "元", "角", "分"
ZERO, WHOLE, ZHENG = "零", "整", "正"

CURRENCY_PREFIXES = ("NT$", "NTD", "TWD", "CNY", "RMB", "HKD", "￥", "¥", "$")


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


def group_to_cn(g, *, pad_zero=True, bare_shi=False):
    """1..9999 的四位组转大写：5005 -> 伍仟零伍。"""
    parts = []
    pending_zero = False
    for idx in (3, 2, 1, 0):
        d = (g // 10 ** idx) % 10
        if d == 0:
            if parts:
                pending_zero = True
            continue
        if parts and pending_zero and pad_zero:
            parts.append(ZERO)
        pending_zero = False
        numeral = DIGITS[d]
        if bare_shi and idx == 1 and d == 1 and not parts:
            numeral = ""  # 老式写法：壹拾 -> 拾
        parts.append(numeral + SECTIONS[idx])
    return "".join(parts)


def int_to_cn(n, *, pad_zero=True, bare_shi=False):
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
        if parts and pad_zero and (pending_zero or g < 1000):
            parts.append(ZERO)
        pending_zero = False
        parts.append(group_to_cn(g, pad_zero=pad_zero, bare_shi=bare_shi) + GROUPS[i])
    return "".join(parts)


def to_upper(text, *, pad_zero=True, whole=WHOLE, prefix="人民币",
             bare_shi=False, whole_after_jiao=False, zero_yuan=True):
    """金额字符串 -> 人民币大写（各风格参数可调）。"""
    negative, yuan, jiao, fen = parse_amount(text)
    pieces = []
    if negative:
        pieces.append("负")
    if yuan == 0 and (jiao or fen):
        if zero_yuan:
            pieces.append(ZERO + YUAN)
    else:
        pieces.append(int_to_cn(yuan, pad_zero=pad_zero, bare_shi=bare_shi) + YUAN)
    if jiao and fen:
        pieces.append(DIGITS[jiao] + JIAO + DIGITS[fen] + FEN)
    elif jiao:
        pieces.append(DIGITS[jiao] + JIAO)
        if whole_after_jiao:
            pieces.append(whole)
    elif fen:
        pieces.append(ZERO + DIGITS[fen] + FEN)
    elif whole:
        pieces.append(whole)
    s = "".join(pieces)
    return (prefix + s) if prefix else s


# 六种变体：(标记, 说明, 覆盖参数)
VARIANTS = (
    ("A", "标准式（人民币前缀·补零·到元加整）", {}),
    ("B", "无前缀式", {"prefix": ""}),
    ("C", "正字式（整→正）", {"whole": ZHENG}),
    ("D", "省零式（不补万位零·零元省略）", {"pad_zero": False, "zero_yuan": False}),
    ("E", "拾字式（壹拾→拾，老式）", {"bare_shi": True}),
    ("F", "角后加整式", {"whole_after_jiao": True}),
)


def _utf8_stdout():
    """Windows 管道/控制台下尽量用 UTF-8 输出，避免中文乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="rmb-uppercase-variants.py",
        description="对同一金额输出多种人民币大写规范变体（前缀/整正/补零等取舍），便于对照。",
    )
    parser.add_argument("amounts", nargs="+", metavar="金额",
                        help="一个或多个金额，如 1234.56、1,234.56")
    args = parser.parse_args(argv)
    _utf8_stdout()
    for raw in args.amounts:
        print(f"输入金额: {raw}")
        for key, label, kwargs in VARIANTS:
            try:
                result = to_upper(raw, **kwargs)
            except AmountError as exc:
                print(f"错误: {exc}", file=sys.stderr)
                return 2
            print(f"  {key} {label}: {result}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
