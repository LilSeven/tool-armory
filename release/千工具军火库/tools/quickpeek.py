#!/usr/bin/env python3
"""quickpeek —— 批量文件首尾行预览。

一次输出多个文本文件的头部和尾部各 N 行，快速了解一批文件的内容。
文件总行数不超过 2N 时全量输出；更长时用省略行标记中段截断。
目录参数会展开为其中（可递归）的文件，可按扩展名过滤；
含 NUL 字节的二进制文件自动跳过。

用法:
    python quickpeek.py [选项] <文件或目录> ...

选项:
    -n, --lines N      头/尾各显示的行数，默认 5
    -r, --recursive    目录参数递归展开
    --ext LIST         只保留这些扩展名（逗号分隔，如 txt,log）
    --encoding ENC     文本编码，默认 utf-8（解码失败自动替换，不报错）

示例:
    python quickpeek.py -n 3 a.log b.log
    python quickpeek.py -n 5 -r --ext txt,log D:/notes
    python quickpeek.py -n 2 "D:/logs/*.log"

退出码: 0 = 至少成功预览一个文件；2 = 没有任何文件被成功预览。
仅使用 Python 标准库。
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from collections import deque


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def is_probably_binary(path: str) -> bool:
    with open(path, "rb") as handle:
        return b"\x00" in handle.read(1024)


def peek_lines(path: str, n: int, encoding: str):
    """返回 (总行数, 展示行列表)。总行数 <= 2N 时全量展示，否则头 N 行 + 省略 + 尾 N 行。"""
    with open(path, "r", encoding=encoding, errors="replace", newline="") as handle:
        head = []
        tail = deque(maxlen=n)
        recent = deque(maxlen=2 * n)
        total = 0
        for line in handle:
            total += 1
            if len(head) < n:
                head.append(line)
            tail.append(line)
            recent.append(line)
    if total <= 2 * n:
        shown = list(recent)
    else:
        shown = head + ["…"] + list(tail)
    return total, [line.rstrip("\r\n") for line in shown]


def expand_inputs(inputs, recursive, exts):
    files, missing = [], []
    for item in inputs:
        if any(ch in item for ch in "*?"):
            for match in sorted(glob.glob(item, recursive=True)):
                if os.path.isfile(match):
                    files.append(match)
            continue
        if os.path.isdir(item):
            if recursive:
                for dirpath, dirnames, filenames in os.walk(item):
                    dirnames.sort()
                    for name in sorted(filenames):
                        files.append(os.path.join(dirpath, name))
            else:
                with os.scandir(item) as it:
                    files.extend(e.path for e in sorted(it, key=lambda e: e.name)
                                 if e.is_file())
        elif os.path.isfile(item):
            files.append(item)
        else:
            missing.append(item)
    if exts is not None:
        files = [f for f in files
                 if os.path.splitext(f)[1].lower().lstrip(".") in exts]
    return files, missing


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="quickpeek",
        description="批量输出多个文本文件的头部和尾部各 N 行。",
    )
    parser.add_argument("inputs", nargs="+", metavar="文件或目录",
                        help="要预览的文件、目录（配合 -r）或通配符")
    parser.add_argument("-n", "--lines", type=int, default=5, metavar="N",
                        help="头/尾各显示的行数，默认 5")
    parser.add_argument("-r", "--recursive", action="store_true", help="目录递归展开")
    parser.add_argument("--ext", default="", metavar="TXT,LOG",
                        help="只保留这些扩展名（逗号分隔）")
    parser.add_argument("--encoding", default="utf-8", help="文本编码，默认 utf-8")
    args = parser.parse_args(argv)
    args.lines = max(0, args.lines)

    exts = None
    if args.ext.strip():
        exts = {t.strip().lower().lstrip(".") for t in args.ext.split(",") if t.strip()}

    files, missing = expand_inputs(args.inputs, args.recursive, exts)
    for item in missing:
        print(f"警告: 路径不存在，已跳过: {item}", file=sys.stderr)
    if not files:
        print("错误: 没有可预览的文件。", file=sys.stderr)
        return 2

    ok_count = 0
    for index, path in enumerate(files):
        if index:
            print()
        try:
            if is_probably_binary(path):
                print(f"==> {path} <==  [疑似二进制文件，已跳过]")
                continue
            total, lines = peek_lines(path, args.lines, args.encoding)
        except OSError as exc:
            print(f"==> {path} <==  [读取失败: {exc}]", file=sys.stderr)
            continue
        print(f"==> {path} <==  (共 {total} 行)")
        if not lines:
            print("（空文件）")
        else:
            print("\n".join(lines))
        ok_count += 1
    return 0 if ok_count else 2


if __name__ == "__main__":
    _force_utf8_stdio()
    sys.exit(main())
