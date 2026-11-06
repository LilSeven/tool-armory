#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字符级 diff：用 difflib 对两文件先按行配对，再做字符级比较，高亮行内被修改的具体字符。

先用 difflib 按行对齐旧/新文件；对内容不同的行对，把行拆成单个字符
再用 difflib 对齐一次，只把真正被改/删/增的字符高亮出来
（旧行改动字符=红色反色、新行改动字符=绿色反色；反色同时能让行内
多出/缺失的空格、Tab 等不可见字符现形），未变化的字符不着色。
适合中文句子、配置项取值等无空格文本或小改动场景。
两文件完全相同时不输出，退出码 0。

用法:
    python char-level-diff.py OLD NEW [-U N] [--style ansi|mark] [--color auto|always|never]
    -U/--context 为变化点两侧保留的相同行数（缺省 3，0=不显示相同行）。

示例:
    python char-level-diff.py old.txt new.txt
    python char-level-diff.py a.cfg b.cfg -U 1 --color always
    python char-level-diff.py a.txt b.txt --style mark   # 文本标记 [-旧字符-] {+新字符+}
"""

import argparse
import difflib
import os
import sys

RESET = "\033[0m"
DIM, RED, GREEN = "\033[2m", "\033[31m", "\033[32m"
CHG_OLD, CHG_NEW = "\033[1;7;31m", "\033[1;7;32m"  # 行内改动字符：加粗+反色


def _utf8_stdout():
    """尽量把 stdout 切到 UTF-8，避免 Windows 控制台中文乱码。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _color_enabled(mode):
    if mode == "always":
        return True
    if mode == "never":
        return False
    return (sys.stdout.isatty()
            and not os.environ.get("NO_COLOR")
            and os.environ.get("TERM", "") != "dumb")


def _make_paint(enabled):
    def paint(text, code):
        if not enabled or not code:
            return text
        return code + text + RESET
    return paint


def _read_lines(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8", "replace").splitlines()


def _inline_marks(old, new, paint, style):
    """对一行对做字符级对齐，返回 (标记后的旧行, 标记后的新行)。"""
    a, b = list(old), list(new)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    o_parts, n_parts = [], []
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op == "equal":
            seg = "".join(a[a1:a2])
            o_parts.append((False, seg))
            n_parts.append((False, seg))
            continue
        if a2 > a1:
            o_parts.append((True, "".join(a[a1:a2])))
        if b2 > b1:
            n_parts.append((True, "".join(b[b1:b2])))

    def join(parts, code, pre, post):
        buf = []
        for changed, seg in parts:
            if not changed:
                buf.append(seg)
            elif style == "mark":
                buf.append(pre + seg + post)
            else:
                buf.append(paint(seg, code))
        return "".join(buf)

    return join(o_parts, CHG_OLD, "[-", "-]"), join(n_parts, CHG_NEW, "{+", "+}")


def render(old_lines, new_lines, old_label, new_label, ctx, paint, style):
    ops = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False).get_opcodes()
    if all(op == "equal" for op, _a1, _a2, _b1, _b2 in ops):
        return []
    num_w = max(3, len(str(max(len(old_lines), len(new_lines), 1))))
    out = [paint(f"--- {old_label}", DIM), paint(f"+++ {new_label}", DIM)]

    def no(n):
        return f"{n:>{num_w}}" if n else " " * num_w

    def gutter(o, n, sign, text):
        return f"{no(o)} {no(n)} {sign} {text}"

    def ctx_rows(a1, a2, b1):
        total = a2 - a1
        if total > 2 * ctx:
            head = list(range(a1, a1 + ctx))
            tail = list(range(a2 - ctx, a2))
            skip = total - 2 * ctx
        else:
            head, tail, skip = list(range(a1, a2)), [], 0
        for i in head:
            out.append(gutter(i + 1, b1 + (i - a1) + 1, " ", old_lines[i]))
        if skip:
            out.append(paint(" " * (2 * num_w + 4)
                             + f"... skipped {skip} identical lines ...", DIM))
        for i in tail:
            out.append(gutter(i + 1, b1 + (i - a1) + 1, " ", old_lines[i]))

    for op, a1, a2, b1, b2 in ops:
        if op == "equal":
            ctx_rows(a1, a2, b1)
        elif op == "replace":
            olds, news = old_lines[a1:a2], new_lines[b1:b2]
            for i in range(max(len(olds), len(news))):
                has_o, has_n = i < len(olds), i < len(news)
                o_num = a1 + i + 1 if has_o else 0
                n_num = b1 + i + 1 if has_n else 0
                if has_o and has_n:
                    o_txt, n_txt = _inline_marks(olds[i], news[i], paint, style)
                elif has_o:
                    o_txt, n_txt = paint(olds[i], RED), ""
                else:
                    o_txt, n_txt = "", paint(news[i], GREEN)
                if has_o:
                    out.append(gutter(o_num, n_num, "-", o_txt))
                if has_n:
                    out.append(gutter(o_num, n_num, "+", n_txt))
        elif op == "delete":
            for i in range(a1, a2):
                out.append(gutter(i + 1, 0, "-", paint(old_lines[i], RED)))
        else:  # insert
            for j in range(b1, b2):
                out.append(gutter(0, j + 1, "+", paint(new_lines[j], GREEN)))
    return out


def main(argv=None):
    _utf8_stdout()
    ap = argparse.ArgumentParser(
        description="先按行配对、再做字符级比较并高亮行内被修改字符的 diff 查看器。")
    ap.add_argument("old", help="旧文件")
    ap.add_argument("new", help="新文件")
    ap.add_argument("-U", "--context", type=int, default=3,
                    help="变化点两侧保留的相同行数(缺省 3，0=不显示)")
    ap.add_argument("--style", choices=("ansi", "mark"), default="ansi",
                    help="标记风格：ansi=颜色高亮，mark=文本标记 [-..-] {+..+}")
    ap.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                    help="着色模式(缺省 auto)")
    args = ap.parse_args(argv)

    try:
        old_lines = _read_lines(args.old)
        new_lines = _read_lines(args.new)
    except OSError as exc:
        print(f"错误: 读取失败: {exc}", file=sys.stderr)
        return 2

    paint = _make_paint(_color_enabled(args.color) and args.style == "ansi")
    for line in render(old_lines, new_lines, args.old, args.new,
                       max(0, args.context), paint, args.style):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
