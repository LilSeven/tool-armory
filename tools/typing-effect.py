#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打字机回放 —— 把文本或文件以打字机逐字效果输出。

将文本（命令行参数、文件或标准输入）按设定速度逐字符打印到终端，
模拟老式打字机的回放效果；可调整每秒字符数与换行停顿。

用法:
    python typing-effect.py "Hello, world!"
    python typing-effect.py -f story.txt --cps 25 --pause 0.3
    echo hello | python typing-effect.py -f -

选项:
    -f, --file PATH   从文件读取文本；PATH 为 - 时读标准输入
    --cps FLOAT       每秒打印的字符数（默认 15，越大越快）
    --pause FLOAT     每换一行额外停顿的秒数（默认 0.25）
    --no-newline      结束时不额外补换行

示例命令:
    python -I typing-effect.py "你好，世界！Hello!"
    python -I typing-effect.py -f README.md --cps 40

退出码: 0 正常（含 Ctrl+C 中断）；1 读取失败；2 参数错误。
"""
import argparse
import sys
import time
from pathlib import Path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="typing-effect", description="打字机回放：逐字输出文本或文件")
    parser.add_argument("text", nargs="?", help="要回放的文本；为 - 时读标准输入")
    parser.add_argument("-f", "--file", help="从文件读取文本；为 - 时读标准输入")
    parser.add_argument("--cps", type=float, default=15.0,
                        help="每秒打印字符数（默认 15）")
    parser.add_argument("--pause", type=float, default=0.25,
                        help="换行时的额外停顿秒数（默认 0.25）")
    parser.add_argument("--no-newline", action="store_true",
                        help="打印结束后不补换行")
    args = parser.parse_args(argv)
    if args.cps <= 0:
        parser.error("--cps 必须大于 0")
    if args.pause < 0:
        parser.error("--pause 不能为负数")
    return args


def load_text(args) -> str:
    """按优先级取文本：-f/--file > 位置参数 > 管道 stdin。"""
    if args.file is not None:
        if args.file == "-":
            return sys.stdin.read()
        return Path(args.file).read_text(encoding="utf-8", errors="replace")
    if args.text is not None:
        if args.text == "-":
            return sys.stdin.read()
        return args.text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def typewriter(text: str, cps: float, pause: float, end_newline: bool = True) -> int:
    """逐字符打印并即时刷新，返回打印的字符数。"""
    out = sys.stdout
    delay = 1.0 / cps
    count = 0
    for ch in text:
        out.write(ch)
        out.flush()
        count += 1
        time.sleep(pause if ch == "\n" else delay)
    if end_newline and text and not text.endswith("\n"):
        out.write("\n")
        out.flush()
    return count


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        text = load_text(args)
    except OSError as exc:
        print("错误：无法读取文本来源：%s" % exc, file=sys.stderr)
        return 1
    try:
        typewriter(text, args.cps, args.pause, not args.no_newline)
    except KeyboardInterrupt:
        try:
            sys.stdout.write("\n")
            sys.stdout.flush()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
