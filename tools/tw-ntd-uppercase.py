#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tw-ntd-uppercase —— 按台湾票据规范把金额转为新台币中文大写。

用途：
    把阿拉伯金额转换为新台币票据大写，供票据/凭证填写与核对。
    规则要点：
      * 元位写作「圆」，角、分照实转换；金额到「圆」为止（无角分）
        末尾加「整」；仅有角无分时角后也加「整」；有分则不加尾字。
      * 10~19 写「壹拾…」而非「拾…」（票据防篡改）；跨节空档补「零」
        （如 100050000 -> 壹亿零伍万）。
      * 默认用简体用字（壹贰叁…万 亿 圆）；加 --trad 切换台湾正体用字
        （壹貳參…萬 億 圓，万亿位写作「兆」）。

示例命令：
    python -I tw-ntd-uppercase.py 1234.56
    python -I tw-ntd-uppercase.py 1000 0.05 107000.53
    python -I tw-ntd-uppercase.py --trad --prefix 1234.56
    python -I tw-ntd-uppercase.py --bare 999999999999.99

输入格式：
    支持 1234.56、1,234.56、NT$1,234.56、￥500、-12.34（负数）等；
    小数最多两位，超出两位按错误处理（退出码 2）。
    整数部分上限 1亿亿（10^16），超出报错退出码 2。
    --prefix 后跟金额样式的词（如 --prefix 1234.56）时，该词按金额处理、
    --prefix 退回默认货币名（货币名不会以数字开头，据此消歧义）。
"""

import argparse
import re
import sys

ZERO = "零"
JIAO = "角"
FEN = "分"
WHOLE = "整"

# 简体（默认）与台湾正体两套用字。
SIMPL = {
    "digits": "零壹贰叁肆伍陆柒捌玖",
    "sections": ("", "拾", "佰", "仟"),
    "groups": ("", "万", "亿", "万亿"),
    "yuan": "圆",
}
TRAD = {
    "digits": "零壹貳參肆伍陸柒捌玖",
    "sections": ("", "拾", "佰", "仟"),
    "groups": ("", "萬", "億", "兆"),
    "yuan": "圓",
}

CURRENCY_PREFIXES = ("NT$", "NTD", "TWD", "CNY", "RMB", "HKD", "￥", "¥", "$")


class AmountError(ValueError):
    """金额无法解析或超出表示范围。"""


def parse_amount(text):
    """解析金额字符串 -> (是否负数, 圆整数, 角, 分)。"""
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


def group_to_cn(g, cs, *, pad_zero=True):
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
        parts.append(cs["digits"][d] + cs["sections"][idx])
    return "".join(parts)


def int_to_cn(n, cs, *, pad_zero=True):
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
        parts.append(group_to_cn(g, cs, pad_zero=pad_zero) + cs["groups"][i])
    return "".join(parts)


def to_upper(text, *, cs=SIMPL, prefix="", zero_yuan=True):
    """金额字符串 -> 新台币大写（圆/角/分，末尾「整」）。"""
    negative, yuan, jiao, fen = parse_amount(text)
    pieces = []
    if negative:
        pieces.append("负")
    if yuan == 0 and (jiao or fen):
        if zero_yuan:
            pieces.append(ZERO + cs["yuan"])
    else:
        pieces.append(int_to_cn(yuan, cs) + cs["yuan"])
    if jiao and fen:
        pieces.append(cs["digits"][jiao] + JIAO + cs["digits"][fen] + FEN)
    elif jiao:
        pieces.append(cs["digits"][jiao] + JIAO + WHOLE)
    elif fen:
        pieces.append(ZERO + cs["digits"][fen] + FEN)
    else:
        pieces.append(WHOLE)
    s = "".join(pieces)
    return (prefix + s) if prefix else s


def _utf8_stdout():
    """Windows 管道/控制台下尽量用 UTF-8 输出，避免中文乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _looks_like_amount(token):
    """宽松判断一个裸词是否金额样式（货币名不会以数字开头）。"""
    t = str(token).strip()
    for ch in (",", "，", " ", "\u00a0", "\t"):
        t = t.replace(ch, "")
    for p in CURRENCY_PREFIXES:
        if t.startswith(p):
            t = t[len(p):]
            break
    if t[:1] in ("+", "-"):
        t = t[1:]
    return bool(t) and t[0].isdigit()


def _defuse_prefix_argv(argv):
    """预处理参数：--prefix 后紧跟金额样式的裸词时，把它还给位置参数。

    --prefix 是 nargs='?' 可选值选项，照抄 `--prefix 1234.56` 这类写法时，
    argparse 会把 "1234.56" 当作前缀名吞掉，导致必需的「金额」位置参数缺失
    （报 the following arguments are required: 金额）。货币名不可能以数字
    开头，故把金额样式的词退回为位置参数，--prefix 退回自动货币名。
    """
    out = []
    for i, tok in enumerate(argv):
        if (tok == "--prefix" and i + 1 < len(argv)
                and _looks_like_amount(argv[i + 1])):
            out.append("--prefix=auto")
        else:
            out.append(tok)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="tw-ntd-uppercase.py",
        description="按台湾票据规范把金额转为新台币大写（圆/角/分，末尾「整」）。",
        allow_abbrev=False,
    )
    parser.add_argument("amounts", nargs="+", metavar="金额",
                        help="一个或多个金额，如 1234.56、1,234.56、NT$500")
    parser.add_argument("--trad", action="store_true",
                        help="用台湾正体用字（貳參陸萬億圓，兆=万亿）")
    parser.add_argument("--prefix", nargs="?", const="auto", default="", metavar="名称",
                        help="结果前加货币名；--prefix 不带值时用「新台币/新臺幣」；"
                             "自定义名可用 --prefix=名称 或 --prefix 名称"
                             "（名称若写成金额样式则自动按金额处理并退回默认名）")
    parser.add_argument("--bare", action="store_true",
                        help="每行只输出大写金额，不回显输入")
    raw_argv = sys.argv[1:] if argv is None else list(argv)
    args = parser.parse_args(_defuse_prefix_argv(raw_argv))
    _utf8_stdout()
    cs = TRAD if args.trad else SIMPL
    if args.prefix == "auto":
        prefix = "新臺幣" if args.trad else "新台币"
    else:
        prefix = args.prefix
    for raw in args.amounts:
        try:
            result = to_upper(raw, cs=cs, prefix=prefix)
        except AmountError as exc:
            print(f"错误: {exc}", file=sys.stderr)
            return 2
        print(result if args.bare else f"{raw} => {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
