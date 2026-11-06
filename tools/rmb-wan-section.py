#!/usr/bin/env python3
"""rmb-wan-section —— 万进制分节显示。

按中文习惯给数字加分节符：默认万进制——以小数点为锚，整数部分自右向左
每 4 位一节（1,0000,0000 即 1 亿），保证每一节都是完整的“万/亿”段；
也可用 -g 3 选择常规千分位（每 3 位一节）。

示例命令：
  python rmb-wan-section.py 12345678.9            # 1234,5678.9
  python rmb-wan-section.py 12345678.9 -g 3       # 12,345,678.9（千分位）
  python rmb-wan-section.py 100000000 1234567     # 1,0000,0000  123,4567
  seq 1 3 | python rmb-wan-section.py             # 从 stdin 逐行读取

说明：
  * 分节只作用于整数部分；小数部分原样保留（含位数与末尾 0）；
  * 输入允许千分位逗号、全角逗号、正负号、全角数字；
  * 关于 12345678.9：万进制分节以小数点为锚，只分整数部分
    12345678 -> 1234,5678，故默认输出 1234,5678.9（即 1234 万 5678.9 元）。
    任务描述中的示例 1,2345,678.9 是把小数位并入数字串一起按 4 位切分
    （1|2345|6789）再回插小数点的结果，每节不再是完整的“万”段；
    如需复现该排版可用 --naive（分节位 4 时输出 1,2345,678.9）；
  * 无法识别的行输出到 stderr 且退出码为 2，其余行照常输出。
"""

import argparse
import re
import sys

# 全角数字/小数点/逗号/正负号 -> 半角
_FW = str.maketrans("０１２３４５６７８９．，－＋", "0123456789.,-+")


class CliError(Exception):
    """用户可修正的错误（参数等），退出码 2。"""


def section_int(int_part: str, size: int, sep: str) -> str:
    """整数部分自右向左每 size 位一节，节间用 sep 连接。"""
    if len(int_part) <= size:
        return int_part
    groups = []
    s = int_part
    while len(s) > size:
        groups.append(s[-size:])
        s = s[:-size]
    groups.append(s)
    return sep.join(reversed(groups))


def normalize(raw: str):
    """清洗输入，返回 (纯数字串, 是否为负)；无法识别抛 ValueError。"""
    s = raw.strip().translate(_FW)
    for ch in (",", "'", "_", " "):
        s = s.replace(ch, "")
    if not s:
        raise ValueError("空输入")
    neg = s.startswith("-")
    if s[0] in "+-":
        s = s[1:]
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", s):
        raise ValueError(f"无法识别的数字: {raw!r}")
    return s, neg


def convert(raw: str, size: int, sep: str, naive: bool = False) -> str:
    s, neg = normalize(raw)
    if naive:
        # 把整数位与小数位连成一串数字、自右每 size 位切分、再回插小数点；
        # 仅用于复现“小数位计入分节”的特殊排版（如 12345678.9 -> 1,2345,678.9）
        int_part, _, frac = s.partition(".")
        digits = int_part.lstrip("0") or "0"
        if frac:
            digits += frac
        groups = []
        t = digits
        while len(t) > size:
            groups.append(t[-size:])
            t = t[:-size]
        groups.append(t)
        body = sep.join(reversed(groups))
        if frac:
            body = body[:-len(frac)] + "." + body[-len(frac):]
    else:
        int_part, _, frac = s.partition(".")
        int_part = int_part.lstrip("0") or "0"
        body = section_int(int_part, size, sep)
        if frac:
            body += "." + frac
    return ("-" + body) if neg else body


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="rmb-wan-section",
        description="按中文习惯分节显示数字：万进制（默认）或常规千分位。",
    )
    ap.add_argument("numbers", nargs="*",
                    help="待分节的数字；省略时从 stdin 逐行读取")
    ap.add_argument("-g", "--group", type=int, choices=(3, 4), default=4,
                    help="分节位数：4=万进制（默认），3=千分位")
    ap.add_argument("--sep", default=",", help="分节符（默认英文逗号）")
    ap.add_argument("--naive", action="store_true",
                    help="整数位+小数位连成一串按 N 位切分后再回插小数点"
                         "（复现 12345678.9 -> 1,2345,678.9 式排版），不推荐用于金额")
    args = ap.parse_args(argv)

    if not args.sep:
        raise CliError("--sep 不能为空字符串")

    raw_inputs = args.numbers
    if not raw_inputs:
        raw_inputs = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]

    failed = 0
    out_lines = []
    for raw in raw_inputs:
        try:
            out_lines.append(convert(raw, args.group, args.sep, args.naive))
        except ValueError as exc:
            failed += 1
            print(f"错误：{exc}", file=sys.stderr)
    sys.stdout.write("".join(l + "\n" for l in out_lines))
    return 2 if failed else 0


def run(argv=None) -> int:
    try:
        return main(argv)
    except CliError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(run())
