#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日志轮询跟踪 —— 类 tail -f：轮询读取日志新增行，按关键字过滤/高亮后输出。

默认从文件末尾开始跟踪（--from-start 则先输出已有内容）；-k 可多次指定，
任一关键字命中即显示；-i 忽略大小写；--color always 强制对命中关键字
ANSI 高亮；检测到文件被截断/轮转时自动从头重读；--run-for 秒数到后自动
退出（便于脚本化测试），Ctrl+C 随时退出。

示例命令:
    python log-follow-filter.py app.log -k ERROR -k Exception
    python log-follow-filter.py app.log -k error -i --color always --from-start
    python log-follow-filter.py app.log --run-for 10 --interval 0.5
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time


def setup_stdio() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def build_matcher(keywords, ignore_case: bool):
    if not keywords:
        return None
    return re.compile("|".join(re.escape(k) for k in keywords),
                      re.IGNORECASE if ignore_case else 0)


def make_highlighter(pattern, color: bool):
    if pattern is None or not color:
        return lambda s: s

    def hl(s: str) -> str:
        return pattern.sub(lambda m: f"\x1b[1;31m{m.group(0)}\x1b[0m", s)

    return hl


def follow(path: str, args) -> None:
    pat = build_matcher(args.keyword, args.ignore_case)
    color = (args.color == "always") or (args.color == "auto" and sys.stdout.isatty())
    hl = make_highlighter(pat, color)
    print(f"[*] 跟踪 {path}   interval={args.interval}s   "
          f"关键字={args.keyword or '(全部行)'}   Ctrl+C 退出", file=sys.stderr, flush=True)

    pending = b""
    start = time.monotonic()
    with open(path, "rb") as f:
        if args.from_start:
            pos = f.seek(0, os.SEEK_SET)
        else:
            pos = f.seek(0, os.SEEK_END)
        while True:
            if args.run_for and (time.monotonic() - start) >= args.run_for:
                break
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size < pos:  # 被截断或轮转
                print("[*] 检测到文件被截断/轮转，从头重读", file=sys.stderr, flush=True)
                f.seek(0)
                pos = 0
                pending = b""
            elif size > pos:
                f.seek(pos)
                data = f.read(size - pos)
                pos += len(data)
                pending += data
                *complete, pending = pending.split(b"\n")
                for raw in complete:
                    text = raw.decode(args.encoding, "replace").rstrip("\r")
                    if pat is None or pat.search(text):
                        print(hl(text), flush=True)
            time.sleep(args.interval)
    if args.run_for:
        print(f"[*] 已跟踪 {time.monotonic() - start:.1f}s，按 --run-for 退出", file=sys.stderr)


def main(argv=None) -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(
        description="类 tail -f：轮询读取日志新增行，按关键字过滤或高亮后输出")
    ap.add_argument("logfile", help="要跟踪的日志文件")
    ap.add_argument("-k", "--keyword", action="append", default=[],
                    help="过滤关键字，可多次指定 (任一命中即显示; 缺省显示全部)")
    ap.add_argument("-i", "--ignore-case", action="store_true", help="关键字匹配忽略大小写")
    ap.add_argument("--interval", type=float, default=1.0, help="轮询间隔秒数 (默认 1.0)")
    ap.add_argument("--run-for", type=float, default=0.0,
                    help="跟踪指定秒数后自动退出 (0=一直跟踪，默认)")
    ap.add_argument("--from-start", action="store_true", help="先输出文件已有内容再跟踪 (缺省从文件末尾开始)")
    ap.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                    help="关键字高亮 (auto=输出为终端时启用)")
    ap.add_argument("--encoding", default="utf-8", help="日志文件编码 (默认 utf-8)")
    args = ap.parse_args(argv)

    try:
        follow(args.logfile, args)
    except FileNotFoundError:
        print(f"错误: 文件不存在: {args.logfile}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n[*] 已退出", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
