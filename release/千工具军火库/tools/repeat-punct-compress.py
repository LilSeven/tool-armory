#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重复标点压缩(repeat-punct-compress)

把 ！！！、？？？、？！？！、!?? 等重复或混叠的标点压缩为规范形式：
  · 纯重复(！！！/？？？/!!!)      -> 折叠为单个符号
  · 问叹混叠(？！？！/！？！？)    -> 折叠为单个强调问叹，默认保留首次出现
                                      的符号顺序去重，可用 --order qe|eq
                                      固定为“？！”或“！？”
  · --mode strict                  -> 一律折叠为该串末尾的单个符号
                                      (？！？！ -> ！)
省略号(……/...)不参与压缩。

用法:
  python -I repeat-punct-compress.py [输入文件] [-o 输出文件]
      [--mode emphatic|strict] [--order first|qe|eq] [--stat]

示例命令:
  printf '真的！！！吗？？？' | python -I repeat-punct-compress.py
  python -I repeat-punct-compress.py input.txt -o output.txt --mode strict
  printf '搞什么？！？！' | python -I repeat-punct-compress.py --order qe
不指定输入文件时读取 stdin；不指定 -o 时结果写到 stdout。
"""
import argparse
import re
import sys

for _s in (sys.stdout, sys.stderr, sys.stdin):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace", newline="")

RUN_RE = re.compile(r"[!！?？]{2,}")


def compress_run(run, mode, order):
    """把一串重复/混叠标点折叠为规范形式。"""
    if mode == "strict":
        return run[-1]
    uniq = []
    for ch in run:
        if ch not in uniq:
            uniq.append(ch)
    if order == "qe":
        uniq.sort(key=lambda c: 0 if c in "？?" else 1)
    elif order == "eq":
        uniq.sort(key=lambda c: 0 if c in "！!" else 1)
    return "".join(uniq)


def compress_text(text, mode, order):
    stats = {"runs": 0, "changed": 0, "removed": 0}

    def _repl(m):
        run = m.group(0)
        stats["runs"] += 1
        new = compress_run(run, mode, order)
        if new != run:
            stats["changed"] += 1
            stats["removed"] += len(run) - len(new)
        return new

    return RUN_RE.sub(_repl, text), stats


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="压缩 ！！！、？！？！ 等重复或混叠标点为规范形式")
    ap.add_argument("input", nargs="?", help="输入文件(缺省读 stdin)")
    ap.add_argument("-o", "--output", help="输出文件(缺省写 stdout)")
    ap.add_argument("--mode", choices=("emphatic", "strict"),
                    default="emphatic",
                    help="emphatic: 混叠折叠为单个强调问叹(默认)；"
                         "strict: 一律折叠为末尾单个符号")
    ap.add_argument("--order", choices=("first", "qe", "eq"), default="first",
                    help="混叠符号顺序: first=按首次出现(默认), qe=？！, eq=！？")
    ap.add_argument("--stat", action="store_true", help="向 stderr 输出统计")
    args = ap.parse_args(argv)

    if args.input:
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    result, stats = compress_text(text, args.mode, args.order)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(result)
    else:
        sys.stdout.write(result)

    if args.stat:
        sys.stderr.write(
            "[repeat-punct-compress] 标点串 {runs} 处，压缩 {changed} 处，"
            "删去 {removed} 个字符\n".format(**stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
