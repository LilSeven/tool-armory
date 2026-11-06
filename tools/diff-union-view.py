#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并对照视图 (diff-union-view)。

用途:
    对比两个版本的文本文件, 生成"合并对照视图":
      * 公共行只展示一份;
      * 替换的行成对相邻展示, 用 '!' 标记高亮;
      * 纯删除用 '-', 纯新增用 '+'。
    每行带旧/新行号, 可选 ANSI 彩色(旧内容红色 / 新内容绿色, 替换对加粗)。

示例命令:
    python diff-union-view.py old.txt new.txt
    python diff-union-view.py old.txt new.txt --color always
    python diff-union-view.py --selftest

仅用 Python 标准库, 单文件; Windows / Git Bash 可用。
"""

import argparse
import difflib
import sys


def _setup_stdio():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _read_text(src):
    if src == "-":
        return sys.stdin.read()
    with open(src, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def build_rows(old_lines, new_lines):
    """返回 [(marker, old_no|None, new_no|None, text, side)]。

    marker: ' '=公共, '!'=替换对成员, '-'=纯删除, '+'=纯新增;
    side:   'both' / 'old' / 'new'。
    """
    rows = []
    sm = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                rows.append((" ", i1 + k + 1, j1 + k + 1, old_lines[i1 + k], "both"))
        elif tag == "replace":
            no, nn = i2 - i1, j2 - j1
            for k in range(max(no, nn)):
                if k < no and k < nn:
                    rows.append(("!", i1 + k + 1, None, old_lines[i1 + k], "old"))
                    rows.append(("!", None, j1 + k + 1, new_lines[j1 + k], "new"))
                elif k < no:
                    rows.append(("-", i1 + k + 1, None, old_lines[i1 + k], "old"))
                else:
                    rows.append(("+", None, j1 + k + 1, new_lines[j1 + k], "new"))
        elif tag == "delete":
            for k in range(i2 - i1):
                rows.append(("-", i1 + k + 1, None, old_lines[i1 + k], "old"))
        else:  # insert
            for k in range(j2 - j1):
                rows.append(("+", None, j1 + k + 1, new_lines[j1 + k], "new"))
    return rows


def render(rows, old_name, new_name, color):
    wo = max([len(str(r[1])) for r in rows if r[1] is not None] + [2])
    wn = max([len(str(r[2])) for r in rows if r[2] is not None] + [2])

    def paint(code, s):
        return f"\x1b[{code}m{s}\x1b[0m" if color else s

    out = [paint("1", f"--- {old_name}   +++ {new_name}   "
                      "(公共行单份展示, 差异行成对高亮)")]
    for marker, o, n, text, side in rows:
        os_ = str(o).rjust(wo) if o is not None else "--".rjust(wo)
        ns_ = str(n).rjust(wn) if n is not None else "--".rjust(wn)
        prefix = f"{marker} {os_} {ns_} | "
        if marker == " ":
            out.append(prefix + text)
        elif marker == "!":
            out.append(paint("1;31" if side == "old" else "1;32", prefix + text))
        elif side == "old":
            out.append(paint("31", prefix + text))
        else:
            out.append(paint("32", prefix + text))
    return "\n".join(out)


def selftest():
    old = ["alpha", "beta", "gamma", "delta", "tail_old"]
    new = ["alpha", "beta!", "gamma", "epsilon"]
    rows = build_rows(old, new)
    markers = [r[0] for r in rows]
    assert markers == [" ", "!", "!", " ", "!", "!", "-"], markers
    assert rows[1] == ("!", 2, None, "beta", "old"), rows[1]
    assert rows[2] == ("!", None, 2, "beta!", "new"), rows[2]
    assert rows[6] == ("-", 5, None, "tail_old", "old"), rows[6]
    # 公共行 "alpha" 只出现一次
    assert sum(1 for r in rows if r[3] == "alpha") == 1, rows
    plain = render(rows, "old.txt", "new.txt", color=False)
    assert "\x1b[" not in plain
    colored = render(rows, "old.txt", "new.txt", color=True)
    assert "\x1b[1;31m" in colored and "\x1b[1;32m" in colored
    print("selftest PASS: 公共行单份展示; 替换对 '!' 成对高亮; 纯删除 '-' 标记正确")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="diff-union-view",
        description="两版本合并对照视图: 公共行单份, 差异行成对高亮")
    ap.add_argument("old", nargs="?", default="", help="旧版本文件 ('-' 表示 stdin)")
    ap.add_argument("new", nargs="?", default="", help="新版本文件 ('-' 表示 stdin)")
    ap.add_argument("--color", choices=["auto", "always", "never"],
                    default="auto", help="彩色输出模式 (默认 auto: 终端时开启)")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = ap.parse_args(argv)
    _setup_stdio()
    if args.selftest:
        return selftest()
    if not args.old or not args.new:
        ap.error("需要提供 old 与 new 两个文件 (或用 --selftest 运行自测)")
    if args.old == "-" and args.new == "-":
        print("错误: old 与 new 不能同时来自 stdin", file=sys.stderr)
        return 2
    try:
        old_text = _read_text(args.old)
        new_text = _read_text(args.new)
    except OSError as e:
        print(f"错误: 无法读取文件: {e}", file=sys.stderr)
        return 2
    color = args.color == "always" or \
        (args.color == "auto" and sys.stdout.isatty())
    rows = build_rows(old_text.splitlines(), new_text.splitlines())
    print(render(rows, args.old, args.new, color))
    changed = sum(1 for r in rows if r[0] != " ")
    print(f"统计: 展示 {len(rows)} 行, 其中差异行 {changed}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
