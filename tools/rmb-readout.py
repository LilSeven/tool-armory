#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rmb-readout —— 大写金额朗读分段（按亿、万、元分节并加节标注）。

用途：
    长金额口头复核容易读串位。本工具把整数部分按「万亿/亿/万/元」四位一节
    切开，每节给出原始数字与该节大写（含跨节补「零」提示），另给一行带间隔
    的分段朗读和一行连续朗读，方便出纳逐节唱票核对。
    尾数规则：有角有分照写；仅有角时角后加「整」；仅有分时补「零X分」；
    无角分末尾加「整」。

示例命令：
    python -I rmb-readout.py 1234567890.56
    python -I rmb-readout.py 100050000 0.05

输出示例（1234567890.56）：
    金额: 1234567890.56（规范化: 1,234,567,890.56）
      亿节 12 -> 拾贰亿
      万节 3456 -> 叁仟肆佰伍拾陆万
      元节 7890 -> 柒仟捌佰玖拾元
      角分 56 -> 伍角陆分
    分段朗读: 拾贰亿 · 叁仟肆佰伍拾陆万 · 柒仟捌佰玖拾元 · 伍角陆分
    连续朗读: 拾贰亿叁仟肆佰伍拾陆万柒仟捌佰玖拾元伍角陆分

输入格式：
    支持 1234.56、1,234.56、￥1,234.56、-12.34（负数）等；
    小数最多两位，超出两位按错误处理（退出码 2）。
    整数部分上限 1亿亿（10^16），超出报错退出码 2。
"""

import argparse
import re
import sys

DIGITS = "零壹贰叁肆伍陆柒捌玖"
SECTIONS = ("", "拾", "佰", "仟")
GROUPS = ("", "万", "亿", "万亿")
YUAN, JIAO, FEN = "元", "角", "分"
ZERO, WHOLE = "零", "整"

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


def build_readout(text):
    """返回 (逐节展示行列表, 分段朗读片段列表, 规范化金额字符串)。"""
    negative, yuan, jiao, fen = parse_amount(text)
    if yuan >= 10 ** 16:
        raise AmountError("整数部分达到或超过 1亿亿（10^16），超出本工具表示范围")
    groups = []
    n = yuan
    while n:
        groups.append(n % 10000)
        n //= 10000
    if not groups:
        groups = [0]
    top = len(groups) - 1
    lines = []
    spoken = []
    pending_zero = False
    for i in range(top, -1, -1):
        g = groups[i]
        label = (GROUPS[i] or "元") + "节"
        shown = str(g) if i == top else f"{g:04d}"
        if g == 0:
            if i == 0:
                body = "零元" if top == 0 else "（元位空）"
                seg = "零元" if top == 0 else None
            else:
                body = "零"
                seg = None
            pending_zero = True
        else:
            seg = group_to_cn(g)
            # 与标准大写一致的补零规则：前面有整节跳空，或本节不足千位
            if spoken and (pending_zero or g < 1000):
                seg = ZERO + seg
            pending_zero = False
            seg += GROUPS[i] or "元"
            body = seg
        lines.append(f"  {label} {shown} -> {body}")
        if seg:
            spoken.append(seg)
    # 元位整节为空时，朗读补一个「元」收尾
    if top > 0 and groups[0] == 0:
        spoken.append("元")
    if jiao and fen:
        tail = DIGITS[jiao] + JIAO + DIGITS[fen] + FEN
    elif jiao:
        tail = DIGITS[jiao] + JIAO + WHOLE
    elif fen:
        tail = ZERO + DIGITS[fen] + FEN
    else:
        tail = WHOLE
    lines.append(f"  角分 {jiao}{fen} -> {tail}")
    spoken.append(tail)
    if negative:
        spoken.insert(0, "负")
    amount_disp = f"{yuan:,}" + (f".{jiao}{fen}" if (jiao or fen) else "")
    if negative:
        amount_disp = "-" + amount_disp
    return lines, spoken, amount_disp


def _utf8_stdout():
    """Windows 管道/控制台下尽量用 UTF-8 输出，避免中文乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="rmb-readout.py",
        description="把人民币大写金额按亿、万、元分节并加节标注，供出纳口头复核。",
    )
    parser.add_argument("amounts", nargs="+", metavar="金额",
                        help="一个或多个金额，如 1234567890.56")
    args = parser.parse_args(argv)
    _utf8_stdout()
    for raw in args.amounts:
        try:
            lines, spoken, amount_disp = build_readout(raw)
        except AmountError as exc:
            print(f"错误: {exc}", file=sys.stderr)
            return 2
        print(f"金额: {raw}（规范化: {amount_disp}）")
        for ln in lines:
            print(ln)
        print("分段朗读: " + " · ".join(spoken))
        print("连续朗读: " + "".join(spoken))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
