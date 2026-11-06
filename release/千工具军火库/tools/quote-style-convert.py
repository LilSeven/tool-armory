#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""引号风格切换(quote-style-convert)

在中文弯引号“”‘’与直角引号「」『』之间整篇切换：
  弯 -> 直角: 按引号类型配对映射，外双内单 => 外「」内『』；
       未配对的 ’(英文撇号如 don’t)保持原样，不会误转成 』。
  直角 -> 弯: 按嵌套深度配对，第 1 层 -> “”，第 ≥2 层 -> ‘’。
默认不触碰 ASCII 直引号(" 与 ')；--with-ascii 时把成对的 " 一并转换
(ASCII 单引号一律不动，避免破坏 it's 这类撇号)。

用法:
  python -I quote-style-convert.py [输入文件] [-o 输出文件]
      --to corner|curly [--with-ascii] [--stat]

示例命令:
  printf '他说：“外层‘内层’结束”' | python -I quote-style-convert.py --to corner
  python -I quote-style-convert.py input.txt --to curly -o output.txt
  printf 'He said "hi"' | python -I quote-style-convert.py --to corner --with-ascii
不指定输入文件时读取 stdin；不指定 -o 时结果写到 stdout。
"""
import argparse
import sys
from collections import Counter

for _s in (sys.stdout, sys.stderr, sys.stdin):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace", newline="")

C_D_OPEN, C_D_CLOSE = "\u201c", "\u201d"   # “ ”
C_S_OPEN, C_S_CLOSE = "\u2018", "\u2019"   # ‘ ’
K_D_OPEN, K_D_CLOSE = "\u300c", "\u300d"   # 「 」
K_S_OPEN, K_S_CLOSE = "\u300e", "\u300f"   # 『 』


def curly_to_corner(text, with_ascii=False):
    out = []
    warns = []
    stats = {"conv": 0, "kept_apostrophe": 0, "kept_stray": 0, "ascii_conv": 0}
    d_open = s_open = a_open = False
    for ch in text:
        if ch == C_D_OPEN:
            if d_open:
                warns.append("弯双引号“嵌套(前一个未闭合)，保持原样")
                out.append(ch)
                stats["kept_stray"] += 1
            else:
                out.append(K_D_OPEN)
                d_open = True
                stats["conv"] += 1
        elif ch == C_D_CLOSE:
            if d_open:
                out.append(K_D_CLOSE)
                d_open = False
                stats["conv"] += 1
            else:
                warns.append("孤立的弯闭双引号”，保持原样")
                out.append(ch)
                stats["kept_stray"] += 1
        elif ch == C_S_OPEN:
            if s_open:
                warns.append("弯单引号‘嵌套(前一个未闭合)，保持原样")
                out.append(ch)
                stats["kept_stray"] += 1
            else:
                out.append(K_S_OPEN)
                s_open = True
                stats["conv"] += 1
        elif ch == C_S_CLOSE:
            if s_open:
                out.append(K_S_CLOSE)
                s_open = False
                stats["conv"] += 1
            else:
                # 无配对开引号的 ’ 视为英文撇号(don’t)，保留原样
                out.append(ch)
                stats["kept_apostrophe"] += 1
        elif with_ascii and ch == '"':
            if a_open:
                out.append(K_D_CLOSE)
                a_open = False
            else:
                out.append(K_D_OPEN)
                a_open = True
            stats["ascii_conv"] += 1
        else:
            out.append(ch)
    if d_open:
        warns.append("有弯双引号未闭合")
    if s_open:
        warns.append("有弯单引号未闭合")
    if a_open:
        warns.append("有 ASCII 双引号未闭合")
    return "".join(out), warns, stats


def corner_to_curly(text, with_ascii=False):
    out = []
    warns = []
    stats = {"conv": 0, "warn": 0}
    depth = 0
    a_open = False
    for ch in text:
        if ch in (K_D_OPEN, K_S_OPEN):
            depth += 1
            out.append(C_D_OPEN if depth == 1 else C_S_OPEN)
            stats["conv"] += 1
        elif ch in (K_D_CLOSE, K_S_CLOSE):
            if depth == 0:
                warns.append("孤立的直角闭引号{}，保持原样".format(ch))
                out.append(ch)
                stats["warn"] += 1
            else:
                out.append(C_D_CLOSE if depth == 1 else C_S_CLOSE)
                depth -= 1
                stats["conv"] += 1
        elif with_ascii and ch == '"':
            if a_open:
                out.append(C_D_CLOSE)
                a_open = False
            else:
                out.append(C_D_OPEN)
                a_open = True
            stats["conv"] += 1
        else:
            out.append(ch)
    if depth > 0:
        warns.append("有 {} 处直角引号未闭合".format(depth))
    return "".join(out), warns, stats


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="在弯引号“”‘’与直角引号「」『』之间整篇切换")
    ap.add_argument("input", nargs="?", help="输入文件(缺省读 stdin)")
    ap.add_argument("-o", "--output", help="输出文件(缺省写 stdout)")
    ap.add_argument("--to", choices=("corner", "curly"), required=True,
                    help="corner=转为「」『』，curly=转为“”‘’")
    ap.add_argument("--with-ascii", action="store_true",
                    help="同时把成对的 ASCII 双引号 \" 一并转换")
    ap.add_argument("--stat", action="store_true", help="向 stderr 输出统计")
    args = ap.parse_args(argv)

    if args.input:
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    if args.to == "corner":
        result, warns, stats = curly_to_corner(text, args.with_ascii)
    else:
        result, warns, stats = corner_to_curly(text, args.with_ascii)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(result)
    else:
        sys.stdout.write(result)

    for msg, cnt in Counter(warns).items():
        sys.stderr.write("[警告] {}(x{})\n".format(msg, cnt))
    if args.stat:
        parts = ["转换 {} 处".format(
            stats.get("conv", 0) + stats.get("ascii_conv", 0))]
        if stats.get("kept_apostrophe"):
            parts.append("撇号保留 {} 处".format(stats["kept_apostrophe"]))
        if stats.get("kept_stray"):
            parts.append("孤立引号保留 {} 处".format(stats["kept_stray"]))
        if stats.get("warn"):
            parts.append("孤立闭引号 {} 处".format(stats["warn"]))
        sys.stderr.write("[quote-style-convert] {}\n".format("，".join(parts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
