#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""grep-with-context —— 带行号与上下文窗口的模式搜索（支持正则与结果着色）。

在文件（或递归目录）中按模式搜索行，输出带文件名与行号的命中行，
可用 -A/-B/-C 控制上下文窗口，组与组之间以 -- 分隔。默认正则匹配，
-F 切换字面量，-i 忽略大小写，-v 反选；命中片段着红色，
文件名/行号着青/绿色（ANSI，Git Bash 与 Windows 终端均可显示）。
二进制文件（前 8KB 含 \\x00）自动跳过，--text 可强制按文本处理。

示例命令:
  python grep-with-context.py "def \\w+" src/ -C 2            # 命中行及前后 2 行
  python grep-with-context.py -i "todo" . --include "*.py"   # 递归目录 + glob 过滤
  python grep-with-context.py -F "a.b(" log.txt -A 3         # 字面量匹配 + 后 3 行
  python grep-with-context.py "err\\d+" app.log --color always > out.txt

退出码: 0=有命中; 1=无命中; 2=参数或 IO 错误。
仅用 Python 标准库。
"""

import argparse
import ctypes
import fnmatch
import os
import re
import sys
from pathlib import Path

C_RESET = "\x1b[0m"
C_FILE = "\x1b[1;36m"
C_LINENO = "\x1b[1;32m"
C_MATCH = "\x1b[1;31m"
C_SEP = "\x1b[1;35m"
_SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules"}


def enable_windows_vt():
    """在 Windows 控制台上启用 ANSI 转义序列（失败则静默忽略）。"""
    if os.name == "nt":
        try:
            k32 = ctypes.windll.kernel32
            h = k32.GetStdHandle(-11)
            mode = ctypes.c_uint32(0)
            if k32.GetConsoleMode(h, ctypes.byref(mode)):
                k32.SetConsoleMode(h, mode.value | 0x0004)
        except Exception:
            pass


def compile_pattern(pat, fixed, word, ignore_case):
    p = re.escape(pat) if fixed else pat
    if word:
        p = r"\b(?:" + p + r")\b"
    try:
        return re.compile(p, re.IGNORECASE if ignore_case else 0)
    except re.error as exc:
        raise SystemExit("错误: 正则表达式无效 %r: %s" % (pat, exc))


def include_match(fpath, includes):
    if not includes:
        return True
    name = fpath.name
    rel = fpath.as_posix()
    return any(fnmatch.fnmatch(name, g) or fnmatch.fnmatch(rel, g) for g in includes)


def collect_files(paths, includes):
    """返回 (文件列表, 缺失路径列表)；目录递归。"""
    files, missing = [], []
    for p in paths:
        if p == "-":
            files.append("-")
            continue
        pp = Path(p)
        if pp.is_dir():
            for root, dirs, names in os.walk(pp):
                dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
                for f in sorted(names):
                    fp = Path(root) / f
                    if include_match(fp, includes):
                        files.append(fp)
        elif pp.is_file():
            files.append(pp)
        else:
            missing.append(p)
    return files, missing


def read_lines(fp, encoding, force_text):
    """读取行；返回 None 表示二进制文件被跳过。"""
    if fp == "-":
        return sys.stdin.read().splitlines()
    try:
        raw = Path(fp).read_bytes()
    except OSError as exc:
        print("警告: 读取失败，已跳过 %s: %s" % (fp, exc), file=sys.stderr)
        return None
    if not force_text and b"\x00" in raw[:8192]:
        return None
    return raw.decode(encoding, errors="replace").splitlines()


def highlight(line, rx, color):
    """给行内命中片段加色；未开启着色时原样返回。"""
    if not color:
        return line
    out, last = [], 0
    for m in rx.finditer(line):
        if m.end() == m.start():
            continue
        out.append(line[last:m.start()])
        out.append(C_MATCH + m.group(0) + C_RESET)
        last = m.end()
    out.append(line[last:])
    return "".join(out)


def emit(fp, label, lines, rx, opts, color):
    """输出单个文件的命中与上下文，返回命中行数。"""
    invert = opts["invert"]
    selected = [i for i, ln in enumerate(lines)
                if bool(rx.search(ln)) != invert]
    if not selected:
        return 0
    before, after = opts["before"], opts["after"]
    ranges = []
    for i in selected:
        lo = max(0, i - before)
        hi = min(len(lines) - 1, i + after)
        if ranges and lo <= ranges[-1][1] + 1:
            ranges[-1][1] = max(ranges[-1][1], hi)
        else:
            ranges.append([lo, hi])
    selset = set(selected)
    first = True
    for lo, hi in ranges:
        if not first:
            print(C_SEP + "--" + C_RESET if color else "--")
        first = False
        for i in range(lo, hi + 1):
            is_match = i in selset
            mark = ":" if is_match else "-"
            body = highlight(lines[i], rx, color) if (is_match and not invert) else lines[i]
            parts = []
            if opts["with_filename"]:
                parts.append((C_FILE + label + C_RESET) if color else label)
            if opts["line_number"]:
                parts.append((C_LINENO + str(i + 1) + C_RESET) if color else str(i + 1))
            sep = (":" if is_match else "-")
            print(sep.join(parts + [body]) if parts else mark + body)
    return len(selected)


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        prog="grep-with-context",
        description="带行号与上下文窗口的模式搜索，支持正则与结果着色。",
    )
    ap.add_argument("pattern", help="搜索模式（默认正则，-F 切换字面量）")
    ap.add_argument("paths", nargs="+", help="文件 / 目录（目录递归）/ - 表示 stdin")
    ap.add_argument("-A", "--after", type=int, default=None, help="命中后附加上下文行数")
    ap.add_argument("-B", "--before", type=int, default=None, help="命中前附加上下文行数")
    ap.add_argument("-C", "--context", type=int, default=0, help="前后各附加 N 行（默认 0）")
    ap.add_argument("-i", "--ignore-case", action="store_true", help="忽略大小写")
    ap.add_argument("-v", "--invert", action="store_true", help="反选：输出不命中的行")
    ap.add_argument("-F", "--fixed", action="store_true", help="按字面量匹配（不解释正则）")
    ap.add_argument("-w", "--word", action="store_true", help="整词匹配")
    ap.add_argument("-n", "--line-number", dest="line_number", action="store_true", default=True)
    ap.add_argument("--no-line-number", dest="line_number", action="store_false",
                    help="不显示行号")
    ap.add_argument("--no-filename", dest="with_filename", action="store_false", default=True,
                    help="不显示文件名前缀")
    ap.add_argument("--color", choices=["auto", "always", "never"], default="auto",
                    help="着色模式（默认 auto：仅终端输出时着色）")
    ap.add_argument("--include", action="append", default=[],
                    help="目录扫描时的文件名 glob 过滤，可多次")
    ap.add_argument("--encoding", default="utf-8", help="文件编码（默认 utf-8）")
    ap.add_argument("-a", "--text", action="store_true", help="不跳过二进制文件")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="[兼容参数] 目录总是递归扫描")
    ap.add_argument("--count", action="store_true", help="只输出每个文件的命中行数")
    args = ap.parse_args(argv)

    if args.color == "always":
        enable_windows_vt()
    color = args.color == "always" or (args.color == "auto" and sys.stdout.isatty())
    after = max(args.after if args.after is not None else args.context, 0)
    before = max(args.before if args.before is not None else args.context, 0)
    rx = compile_pattern(args.pattern, args.fixed, args.word, args.ignore_case)
    opts = {"invert": args.invert, "before": before, "after": after,
            "line_number": args.line_number, "with_filename": args.with_filename}

    files, missing = collect_files(args.paths, args.include)
    for p in missing:
        print("警告: 路径不存在，已跳过: %s" % p, file=sys.stderr)

    total = 0
    for fp in files:
        label = "<stdin>" if fp == "-" else Path(fp).as_posix()
        lines = read_lines(fp, args.encoding, args.text)
        if lines is None:
            continue
        if args.count:
            n = sum(1 for ln in lines if bool(rx.search(ln)) != args.invert)
            if n:
                total += n
                head = ("%s:" % (C_FILE + label + C_RESET)) if color else ("%s:" % label)
                print(head + str(n))
        else:
            total += emit(fp, label, lines, rx, opts, color)

    if missing:
        return 2
    return 0 if total else 1


if __name__ == "__main__":
    sys.exit(main())
