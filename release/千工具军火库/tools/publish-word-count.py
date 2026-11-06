#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""出版版面字数估算 —— 按出版排版口径（行数 × 每行字数）估算版面字数。

口径说明
  · 排版参数为「每行字数」（按全角汉字计；西文/数字/空格按半角 0.5 字折算，
    用 Unicode 东亚宽度判定）与「每面行数」；
  · paragraph 模式（默认）：每个非空段落另起一行并计入段首缩进（默认 2 字），
    段内按宽度折算行数，不足一行的零头按一行计；
    注意：段落应为未硬换行的整段（一行一段），若稿件已手动断行请用 line 模式；
  · line 模式：源文件每个非空行即一个排版行；
  · 版面字数 = 排版总行数 × 每行字数（本工具主口径）；
  · 估算页数 = 排版行数 ÷ 每面行数（向上取整，不足一面按一面），
    按整面计字数 = 页数 × 每面行数 × 每行字数（稿酬核算常用）；
  · 已知页数时可用 --pages 直接换算，无需稿本。

用法
  python publish-word-count.py manuscript.txt
  python publish-word-count.py manuscript.txt --chars-per-line 29 --lines-per-page 27
  python publish-word-count.py manuscript.txt --mode line --indent 0
  python publish-word-count.py --pages 320 --chars-per-line 32 --lines-per-page 25
  cat manuscript.txt | python publish-word-count.py -

仅用 Python 标准库。
"""

import argparse
import math
import sys
import unicodedata


def _setup_stdio():
    for s in (sys.stdout, sys.stderr, sys.stdin):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def decode_auto(data, encoding=None):
    if encoding:
        return data.decode(encoding)
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def char_width(ch):
    return 1.0 if unicodedata.east_asian_width(ch) in ("W", "F") else 0.5


def layout_stats(text, cpl, indent, mode):
    paras = [ln.strip() for ln in text.splitlines()]
    paras = [p for p in paras if p]
    if mode == "line":
        return len(paras), len(paras)
    lines = 0
    for para in paras:
        width = indent + sum(char_width(c) for c in para)
        lines += max(1, math.ceil(width / cpl))
    return len(paras), lines


def main(argv=None):
    _setup_stdio()
    p = argparse.ArgumentParser(description="出版版面字数估算（行数×每行字数，稿酬/篇幅核算）")
    p.add_argument("input", nargs="?", help="稿本文本路径，- 表示标准输入；与 --pages 二选一")
    p.add_argument("--pages", type=int, help="直接给定排版页（面）数，跳过文本估算")
    p.add_argument("--chars-per-line", type=float, default=32.0,
                   help="每行字数，全角计（默认 32）")
    p.add_argument("--lines-per-page", type=int, default=25,
                   help="每面行数（默认 25）")
    p.add_argument("--indent", type=float, default=2.0,
                   help="段首缩进字数（默认 2；--mode line 下忽略）")
    p.add_argument("--mode", choices=("paragraph", "line"), default="paragraph",
                   help="paragraph=每段按宽度折行（默认）；line=源文件每非空行即一个排版行")
    args = p.parse_args(argv)

    if args.chars_per_line <= 0 or args.lines_per_page <= 0:
        p.error("--chars-per-line 与 --lines-per-page 必须为正数")

    if args.pages is not None:
        if args.pages <= 0:
            p.error("--pages 必须为正整数")
        lines = args.pages * args.lines_per_page
        print(f"给定页数        : {args.pages:,} 面")
        print(f"排版行数        : {lines:,} 行 = {args.pages:,} 面 × {args.lines_per_page} 行/面")
        print(f"版面字数        : {lines * args.chars_per_line:,.0f} 字 "
              f"= {lines:,} 行 × {args.chars_per_line:g} 字/行")
        return 0

    if not args.input:
        p.error("需要提供稿本文本路径，或用 --pages 直接指定页数")

    try:
        text = sys.stdin.read() if args.input == "-" else decode_auto(read_bytes(args.input), None)
    except OSError as e:
        print(f"错误: 无法读取输入: {e}", file=sys.stderr)
        return 1
    except UnicodeDecodeError as e:
        print(f"错误: 解码失败: {e}", file=sys.stderr)
        return 1

    paras, lines = layout_stats(text, args.chars_per_line, args.indent, args.mode)
    pages = math.ceil(lines / args.lines_per_page) if lines else 0
    print(f"排版参数        : 每行 {args.chars_per_line:g} 字 × 每面 {args.lines_per_page} 行，"
          f"段首缩进 {args.indent:g} 字，模式 {args.mode}")
    print(f"段落数          : {paras:,}")
    print(f"排版行数        : {lines:,} 行（零头按一行计）")
    print(f"版面字数        : {lines * args.chars_per_line:,.0f} 字 "
          f"= {lines:,} 行 × {args.chars_per_line:g} 字/行")
    print(f"估算页数        : {pages:,} 面（不足一面按一面）")
    print(f"按整面计字数    : {pages * args.lines_per_page * args.chars_per_line:,.0f} 字（稿酬核算常用）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
