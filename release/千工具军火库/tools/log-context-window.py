#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日志上下文查看(log-context-window):定位匹配行并展示前后 N 行上下文。

类似 grep, 但面向排查错误现场: 命中行以 "行号:" 标注, 上下文行以 "行号-"
标注, 两段不相连的上下文之间用 "--" 分隔; 行号默认始终显示。

用法:
    python log-context-window.py [-A N] [-B N] [-C N] [-i] [-F] [-v] PATTERN [FILE ...]
    ... | python log-context-window.py [-C N] PATTERN

选项:
    -A N  匹配行之后 N 行       -B N  匹配行之前 N 行
    -C N  前后各 N 行(默认 2)   -i    忽略大小写
    -F    PATTERN 按普通字符串  -v    反选(展示"不匹配行"的上下文)

示例:
    python -I log-context-window.py -C 3 "ERROR" app.log
    python -I log-context-window.py -B 2 -A 5 "Traceback" app.log
    tail -n 2000 app.log | python -I log-context-window.py -C 2 Timeout

退出码: 找到匹配返回 0; 未找到返回 1; 用法/文件错误返回 2。
仅使用 Python 标准库。
"""

import argparse
import re
import sys
from collections import deque


def _setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _open_line_source(path):
    """返回 (显示名, 文件对象, 是否需要关闭)。"""
    if path == "-":
        try:
            sys.stdin.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
        return "<stdin>", sys.stdin, False
    try:
        return path, open(path, "r", encoding="utf-8", errors="replace"), True
    except OSError as exc:
        print("错误: 无法打开 %s: %s" % (path, exc), file=sys.stderr)
        raise SystemExit(2)


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(
        prog="log-context-window",
        description="定位日志中的匹配行并展示前后 N 行上下文")
    ap.add_argument("pattern", help="正则表达式(-F 时为普通字符串)")
    ap.add_argument("files", nargs="*",
                    help="日志文件(可多个); 缺省或 '-' 表示 stdin")
    ap.add_argument("-A", type=int, default=None, metavar="N", help="匹配行之后 N 行")
    ap.add_argument("-B", type=int, default=None, metavar="N", help="匹配行之前 N 行")
    ap.add_argument("-C", type=int, default=None, metavar="N", help="前后各 N 行(默认 2)")
    ap.add_argument("-i", dest="ignorecase", action="store_true", help="忽略大小写")
    ap.add_argument("-F", dest="fixed", action="store_true", help="按普通字符串匹配")
    ap.add_argument("-v", dest="invert", action="store_true", help="反选")
    args = ap.parse_args(argv)

    ctx = args.C if args.C is not None else 2
    after_n = args.A if args.A is not None else ctx
    before_n = args.B if args.B is not None else ctx
    after_n = max(0, after_n)
    before_n = max(0, before_n)

    try:
        pattern = re.compile(
            re.escape(args.pattern) if args.fixed else args.pattern,
            re.IGNORECASE if args.ignorecase else 0)
    except re.error as exc:
        print("错误: 无效的正则表达式: %s" % exc, file=sys.stderr)
        return 2

    paths = args.files or ["-"]
    prefix_names = len([p for p in paths if p != "-"]) > 1

    def fmt(name, lineno, text, is_match):
        mark = ":" if is_match else "-"
        if prefix_names:
            return "%s:%d%s %s" % (name, lineno, mark, text)
        return "%d%s %s" % (lineno, mark, text)

    found = False
    for path in paths:
        name, fh, do_close = _open_line_source(path)
        before = deque(maxlen=before_n) if before_n > 0 else None
        last_printed = 0
        pending_after = 0
        try:
            for lineno, raw in enumerate(fh, 1):
                text = raw.rstrip("\r\n")
                hit = bool(pattern.search(text)) != args.invert
                if hit:
                    found = True
                    if before:
                        for bl, bt in before:
                            if bl > last_printed:
                                if last_printed and bl > last_printed + 1:
                                    print("--")
                                print(fmt(name, bl, bt, False))
                                last_printed = bl
                    if last_printed and lineno > last_printed + 1:
                        print("--")
                    print(fmt(name, lineno, text, True))
                    last_printed = lineno
                    pending_after = after_n
                elif pending_after > 0:
                    print(fmt(name, lineno, text, False))
                    last_printed = lineno
                    pending_after -= 1
                if before is not None:
                    before.append((lineno, text))
        finally:
            if do_close:
                fh.close()

    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
