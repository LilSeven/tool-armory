#!/usr/bin/env python3
"""终端匹配高亮器 — 用 ANSI 颜色在终端高亮文本中所有正则匹配，不同捕获组不同颜色。

整组匹配 0 用高亮红，捕获组 1..n 依次使用青/黄/绿/品红/蓝等轮换。
支持从文件、stdin 或 --text 读入。

用法：
  python -I regex-paint.py --text '2026-11-01 ERROR disk full' '(\\d{4})-(\\d{2})-(\\d{2})'
  python -I regex-paint.py log.txt '(ERROR|WARN) \\[(?P<mod>[^]]+)\\]'
  cat code.py | python -I regex-paint.py 'def (\\w+)'
  python -I regex-paint.py --text 'hello world' '\\w+' --no-color   # 试试配色
退出码：0 成功；1 无匹配或 IO 错误；2 正则编译失败。
"""
import argparse
import os
import re
import sys

RESET = "\x1b[0m"
GROUP_COLORS = [
    "\x1b[1;31m",  # 亮红 - 整体匹配
    "\x1b[1;36m",  # 亮青
    "\x1b[1;33m",  # 亮黄
    "\x1b[1;32m",  # 亮绿
    "\x1b[1;35m",  # 亮品红
    "\x1b[1;34m",  # 亮蓝
    "\x1b[1;37m",  # 亮白
]


def paint_line(line: str, rx: re.Pattern, use_color: bool) -> str:
    """对一行文本着色：组 0 用 GROUP_COLORS[0]，组 i 用 GROUP_COLORS[i % len]。"""
    pieces = []
    last = 0
    for m in rx.finditer(line):
        pieces.append(line[last : m.start()])
        if use_color:
            # 整体匹配画底色，各捕获组画各自颜色
            seg = ""
            m_start = m.start()
            prev_end = m_start
            spans = []
            for gi in range(1, (m.re.groups or 0) + 1):
                s, e = m.span(gi)
                if s is None or s < 0:
                    continue
                spans.append((s, e, gi))
            spans.sort()
            # 整体匹配范围，把组内文字替换为组颜色
            for s, e, gi in spans:
                seg += line[prev_end:s]
                color = GROUP_COLORS[gi % len(GROUP_COLORS)]
                seg += color + line[s:e] + RESET if e > s else ""
                prev_end = e
            seg += line[prev_end : m.end()]
            pieces.append(GROUP_COLORS[0] + seg + RESET if seg else seg)
        else:
            pieces.append(line[m.start() : m.end()])
        last = m.end()
    pieces.append(line[last:])
    return "".join(pieces)


def main(argv=None):
    ap = argparse.ArgumentParser(description="终端 ANSI 正则匹配高亮器")
    ap.add_argument("file", nargs="?", help="输入文件；省略且无 --text 时读 stdin")
    ap.add_argument("pattern", help="正则表达式")
    ap.add_argument("--text", help="直接高亮该字符串")
    ap.add_argument("-i", "--encoding", default="utf-8")
    ap.add_argument("--flags", default="", help="附加 re 标志：i m s x")
    ap.add_argument("--no-color", action="store_true", help="禁用颜色（仅显示匹配结构）")
    args = ap.parse_args(argv)

    flags = 0
    for c in args.flags:
        flags |= {"i": re.I, "m": re.M, "s": re.S, "x": re.X}.get(c.lower(), 0)
    try:
        rx = re.compile(args.pattern, flags)
    except re.error as exc:
        print(f"错误：正则编译失败: {exc}", file=sys.stderr)
        return 2

    if args.text is not None:
        lines = args.text.split("\n")
    elif args.file:
        try:
            with open(args.file, "r", encoding=args.encoding) as f:
                lines = f.read().split("\n")
        except OSError as exc:
            print(f"错误：读取失败: {exc}", file=sys.stderr)
            return 1
    elif not sys.stdin.isatty():
        lines = sys.stdin.read().split("\n")
    else:
        ap.print_usage(sys.stderr)
        return 1

    use_color = (not args.no_color) and sys.stdout.isatty() or (not args.no_color and os.environ.get("FORCE_COLOR") == "1")
    # 管道/重定向测试时默认仍输出颜色，除非 --no-color；这里简化：默认启用
    use_color = not args.no_color

    total = 0
    for line in lines:
        cnt = len(rx.findall(line)) if rx.groups == 0 else len(list(rx.finditer(line)))
        total += cnt
        print(paint_line(line, rx, use_color))

    if total == 0:
        print(f"（无匹配: '{args.pattern}'）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
