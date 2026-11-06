#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""繁体标点风格转换：弯引号“”‘’与直角引号「」『』互转，适配繁体出版与竖排习惯。

默认把西式弯引号转为 CJK 直角引号（“…”→「…」、‘…’→『…』）；
--to west 则反向（「…」→“…”、『…』→‘…’）。可处理文件或 stdin/stdout 流。

示例命令：
  echo 他说：“你好” | python -I punct-trad-convert.py
  python -I punct-trad-convert.py --to cjk --straight input.txt -o output.txt
  python -I punct-trad-convert.py --to west input.txt > output.txt
"""
import argparse
import sys

FWD = {"\u201c": "\u300c", "\u201d": "\u300d",  # “ ” -> 「 」
       "\u2018": "\u300e", "\u2019": "\u300f"}  # ‘ ’ -> 『 』
REV = {v: k for k, v in FWD.items()}


def convert(text, to="cjk", straight=False):
    """to=cjk 把弯引号(及可选的 ASCII 直引号)转直角引号；to=west 反向。"""
    if to == "cjk":
        mapping = FWD
        straight_open, straight_close = "\u300c", "\u300d"   # 「 」
        straight2_open, straight2_close = "\u300e", "\u300f"  # 『 』
    else:
        mapping = REV
        straight_open, straight_close = "\u201c", "\u201d"
        straight2_open, straight2_close = "\u2018", "\u2019"

    out = []
    level = 0  # 0=期待左引号, 1=已在一层引号内
    for ch in text:
        if ch in mapping:
            out.append(mapping[ch])
        elif straight and ch in ('"', "'"):
            if level == 0:
                out.append(straight_open if ch == '"' else straight2_open)
                level = 1
            else:
                out.append(straight_close if ch == '"' else straight2_close)
                level = 0
        else:
            out.append(ch)
    return "".join(out)


def _read_text(args):
    if args.inputs:
        parts = []
        for p in args.inputs:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                parts.append(f.read())
        return "".join(parts)
    data = sys.stdin.read()
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="弯引号与直角引号互转（繁体标点风格）")
    ap.add_argument("inputs", nargs="*", help="输入文件（缺省读 stdin）")
    ap.add_argument("--to", choices=["cjk", "west"], default="cjk",
                    help="cjk=弯引号转直角(默认)；west=直角转弯引号")
    ap.add_argument("--straight", action="store_true",
                    help="同时把 ASCII 直引号（双/单）按开闭交替转为引号对（仅 --to cjk）")
    ap.add_argument("-o", "--output", help="输出文件（缺省写 stdout）")
    args = ap.parse_args(argv)

    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace", newline="")

    text = _read_text(args)
    result = convert(text, to=args.to, straight=args.straight)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
