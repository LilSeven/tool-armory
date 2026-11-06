#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数字转中文 (num2cn)

把阿拉伯数字转为中文：小写（一二三）与大写（壹贰叁）金额，以及中文序数。
正确处理零的读法规则（中间多个零合并、级末零省略）、十的 "一十/十" 与
"壹拾" 规则。金额支持小数（角/分），序数支持 "第 X" 形式。

用法:
  python num2cn.py 1234567890.56            # 默认输出小写金额
  python num2cn.py 100200304.05 --upper     # 大写（壹贰叁）金额
  python num2cn.py 3 --ordinal              # 序数: 第三
  python num2cn.py 105 --all                # 一次输出全部形式

示例:
  python num2cn.py 100200304.05 --upper
  -> 壹亿零贰拾万零叁佰零肆元零伍分
"""
import argparse
import sys

DIGITS_LO = "零一二三四五六七八九"
DIGITS_UP = "零壹贰叁肆伍陆柒捌玖"
UNITS_LO = ["", "十", "百", "千"]
UNITS_UP = ["", "拾", "佰", "仟"]
GROUPS_LO = ["", "万", "亿", "兆"]
GROUPS_UP = ["", "万", "亿", "兆"]


def _segment(v: int, digits: str, units: str) -> str:
    """0..9999 组内转中文，组内零合并为单个 '零'。"""
    seg = []
    zero_pending = False
    for u in range(3, -1, -1):
        d = v // (10 ** u) % 10
        if d == 0:
            if seg:
                zero_pending = True
            continue
        if zero_pending:
            seg.append("零")
            zero_pending = False
        seg.append(digits[d] + units[u])
    return "".join(seg)


def _int_to_cn(n: int, digits: str, units: str, groups, drop_leading_one: bool) -> str:
    """整数转中文，处理跨组零读法。n >= 0。"""
    if n == 0:
        return "零"
    parts = []  # (组号, 组内数值 0..9999)，从低位到高位
    idx = 0
    while n > 0:
        parts.append((idx, n % 10000))
        n //= 10000
        idx += 1
    result = []
    prev_pos = None  # 上一个非零组的组号
    for pos in range(len(parts) - 1, -1, -1):
        val = parts[pos][1]
        if val == 0:
            continue
        if prev_pos is not None and (pos < prev_pos - 1 or val < 1000):
            # 组间零: 中间有全零组，或本组不足千位（千位为 0）
            result.append("零")
        result.append(_segment(val, digits, units) + groups[pos])
        prev_pos = pos
    text = "".join(result)
    # 小写规则: 开头的 "一十" 读作 "十"（如 10->十, 15->十五, 100000->十万）；
    # 大写保留 "壹拾"
    if drop_leading_one and text.startswith(digits[1] + units[1]):
        text = text[1:]
    return text


def to_amount(value, upper: bool = False) -> str:
    """金额: 整数部分 + 元 + 角分，零角有分时补 '零'。"""
    digits = DIGITS_UP if upper else DIGITS_LO
    units = UNITS_UP if upper else UNITS_LO
    groups = GROUPS_UP if upper else GROUPS_LO
    neg = value < 0
    v = abs(round(float(value) * 100))
    yi = v // 100
    jiao = v // 10 % 10
    fen = v % 10
    out = []
    int_part = _int_to_cn(yi, digits, units, groups, drop_leading_one=not upper)
    out.append(("负" if neg else "") + int_part + "元")
    if jiao == 0 and fen == 0:
        out.append("整")
    else:
        if jiao > 0:
            out.append(digits[jiao] + "角")
        elif fen > 0:
            out.append("零")
        if fen > 0:
            out.append(digits[fen] + "分")
    return "".join(out)


def to_ordinal(value, upper: bool = False) -> str:
    """序数: 第 + 中文数字（小写/大写）。"""
    digits = DIGITS_UP if upper else DIGITS_LO
    units = UNITS_UP if upper else UNITS_LO
    groups = GROUPS_UP if upper else GROUPS_LO
    n = int(value)
    neg = "负" if n < 0 else ""
    return "第" + neg + _int_to_cn(abs(n), digits, units, groups, drop_leading_one=not upper)


def main() -> int:
    ap = argparse.ArgumentParser(description="阿拉伯数字转中文大写/小写金额与序数")
    ap.add_argument("number", help="数字，如 1234.56")
    ap.add_argument("--upper", action="store_true", help="大写（壹贰叁）")
    ap.add_argument("--ordinal", action="store_true", help="输出序数（去掉 '元角分' 语义）")
    ap.add_argument("--all", action="store_true", help="输出小写/大写两种形式")
    args = ap.parse_args()

    try:
        value = float(args.number)
    except ValueError:
        print(f"错误: 不是有效数字: {args.number}", file=sys.stderr)
        return 1

    try:
        if args.ordinal:
            for up in ([False, True] if args.all else [args.upper]):
                print(to_ordinal(value, upper=up))
        elif args.all:
            print("小写: " + to_amount(value, upper=False))
            print("大写: " + to_amount(value, upper=True))
        else:
            print(to_amount(value, upper=args.upper))
    except (OverflowError, ValueError) as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
