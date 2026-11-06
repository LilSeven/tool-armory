#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""忽略空白与大小写的 diff：比较两文件时忽略空白与大小写差异，只看实质内容变化。

比较前先把每行归一化——默认去掉全部空白并把字母转成小写——再做行对齐，
因此缩进调整、行尾空格、Tab 与空格互换、大小写改动都不会被当成变化；
只有实质内容不同的行才以 unified 风格输出（-U 控制上下文行数）。
--keep-ws / --keep-case 可逐项关闭忽略；--ignore-blank-lines 连空行
差异也忽略。无实质差异时不输出、退出码 0；--exit-code 时有实质差异
退出 1（仿 GNU diff），读写出错退出 2。

用法:
    python diff-ignore-ws.py OLD NEW [-U N] [--keep-ws] [--keep-case]
                              [--ignore-blank-lines] [--exit-code] [--color auto|always|never]

示例:
    python diff-ignore-ws.py old.txt new.txt
    python diff-ignore-ws.py a.py b.py -U 1 --keep-case
    python diff-ignore-ws.py old.txt new.txt --exit-code   # 脚本中用退出码判断是否有实质差异
"""

import argparse
import difflib
import os
import sys

RESET = "\033[0m"
DIM, CYAN = "\033[2m", "\033[36m"
RED, GREEN = "\033[31m", "\033[32m"


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


def _normalize(line, ignore_ws, ignore_case):
    s = line
    if ignore_ws:
        s = "".join(s.split())
    if ignore_case:
        s = s.lower()
    return s


def _group_opcodes(ops, u):
    """仿 difflib.get_grouped_opcodes：把 opcode 序列切成若干 hunk。
    相邻变化之间超过 2u 行相同内容时断开；文件开头/末尾的相同行
    只保留 u 行作上下文。"""
    groups, cur = [], []
    last = len(ops) - 1
    for idx, (op, a1, a2, b1, b2) in enumerate(ops):
        if op == "equal":
            length = a2 - a1
            if idx == 0 and length > u:
                if u:
                    cur.append(("equal", a2 - u, a2, b2 - u, b2))
                continue
            if idx == last and length > u:
                if u:
                    cur.append(("equal", a1, a1 + u, b1, b1 + u))
                continue
            if length > 2 * u:
                if u:
                    cur.append(("equal", a1, a1 + u, b1, b1 + u))
                if any(o != "equal" for o, *_rest in cur):
                    groups.append(cur)
                cur = []
                if u:
                    cur.append(("equal", a2 - u, a2, b2 - u, b2))
                continue
        cur.append((op, a1, a2, b1, b2))
    if any(o != "equal" for o, *_rest in cur):
        groups.append(cur)
    return groups


def main(argv=None):
    _utf8_stdout()
    ap = argparse.ArgumentParser(
        description="忽略空白与大小写差异，只比较两文件的实质内容。")
    ap.add_argument("old", help="旧文件")
    ap.add_argument("new", help="新文件")
    ap.add_argument("-U", "--context", type=int, default=3,
                    help="每个变化点周围显示的上下文行数(缺省 3)")
    ap.add_argument("--keep-ws", action="store_true",
                    help="不忽略空白(默认忽略全部空白)")
    ap.add_argument("--keep-case", action="store_true",
                    help="不忽略大小写")
    ap.add_argument("--ignore-blank-lines", action="store_true",
                    help="同时忽略空行(以及仅含空白的行)")
    ap.add_argument("--exit-code", action="store_true",
                    help="发现实质差异时退出码置 1(仿 GNU diff)")
    ap.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                    help="着色模式(缺省 auto)")
    args = ap.parse_args(argv)

    try:
        old_lines = _read_lines(args.old)
        new_lines = _read_lines(args.new)
    except OSError as exc:
        print(f"错误: 读取失败: {exc}", file=sys.stderr)
        return 2

    ignore_ws, ignore_case = not args.keep_ws, not args.keep_case

    def norm(line):
        return _normalize(line, ignore_ws, ignore_case)

    def keep(line):
        return bool(norm(line)) if args.ignore_blank_lines else True

    old_idx = [i for i, ln in enumerate(old_lines) if keep(ln)]
    new_idx = [i for i, ln in enumerate(new_lines) if keep(ln)]
    a = [norm(old_lines[i]) for i in old_idx]
    b = [norm(new_lines[i]) for i in new_idx]
    ops = difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()
    groups = _group_opcodes(ops, max(0, args.context))
    if not groups:
        return 0

    paint = _make_paint(_color_enabled(args.color))
    print(paint(f"--- {args.old}", DIM))
    print(paint(f"+++ {args.new}", DIM))
    for g in groups:
        a_start, a_end = g[0][1], g[-1][2]
        b_start, b_end = g[0][3], g[-1][4]
        if a_end > a_start:
            o_lo = old_idx[a_start] + 1
            o_cnt = old_idx[a_end - 1] - old_idx[a_start] + 1
        else:
            o_lo = old_idx[a_start] if a_start < len(old_idx) else len(old_lines)
            o_cnt = 0
        if b_end > b_start:
            n_lo = new_idx[b_start] + 1
            n_cnt = new_idx[b_end - 1] - new_idx[b_start] + 1
        else:
            n_lo = new_idx[b_start] if b_start < len(new_idx) else len(new_lines)
            n_cnt = 0
        print(paint(f"@@ -{o_lo},{o_cnt} +{n_lo},{n_cnt} @@", CYAN))
        for op, a1, a2, b1, b2 in g:
            if op in ("equal", "delete", "replace"):
                for k in range(a1, a2):
                    ln = old_lines[old_idx[k]]
                    print((" " + ln) if op == "equal" else paint("-" + ln, RED))
            if op in ("insert", "replace"):
                for k in range(b1, b2):
                    print(paint("+" + new_lines[new_idx[k]], GREEN))
    return 1 if args.exit_code else 0


if __name__ == "__main__":
    sys.exit(main())
