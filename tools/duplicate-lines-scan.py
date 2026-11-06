#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文本重复行扫描（duplicate-lines-scan）。

用途：
    统计文本文件（可为大文件，逐行流式读取）中重复次数最多的行 Top N、
    唯一行数与整体重复率（冗余行数 / 计入统计的行数），用于发现刷屏
    日志、模板化输出等冗余内容。

用法：
    python -I duplicate-lines-scan.py <文本文件> [-n TOP] [--encoding ENC]
                                       [--ignore-case] [--min-len N]

示例（Git Bash / Windows）：
    python -I duplicate-lines-scan.py K:/logs/app.log -n 10
    python -I duplicate-lines-scan.py K:/logs/app.log -n 5 --ignore-case

说明：
    * --encoding auto 时按 UTF-8 BOM -> UTF-8 -> GBK -> latin-1 顺序探测；
    * 唯一行内容保存在内存中，行数极多且几乎不重复的文件请留意内存占用；
    * 退出码：0=成功；2=文件不存在或解码失败。
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

SAMPLE_BYTES = 1024 * 1024


def _stdout_utf8() -> None:
    """在 Windows 控制台上尽量用 UTF-8 输出，避免中文乱码或编码报错。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def human_size(n: int) -> str:
    v = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(v)} B"
            return f"{v:.1f} {unit}"
        v /= 1024
    return f"{v:.1f} TB"


def detect_encoding(path: str) -> str:
    """读取开头最多 1MB 样本探测编码；无法确定时回退 latin-1（永不失败）。"""
    with open(path, "rb") as f:
        sample = f.read(SAMPLE_BYTES)
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    for enc in ("utf-8", "gbk"):
        try:
            sample.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def main(argv=None) -> int:
    _stdout_utf8()
    p = argparse.ArgumentParser(
        prog="duplicate-lines-scan", description="统计文本文件重复行 Top N 与整体重复率"
    )
    p.add_argument("file", help="要扫描的文本文件")
    p.add_argument("-n", "--top", type=int, default=10, help="显示前 N 个重复行（默认 10）")
    p.add_argument("--encoding", default="auto", help="文件编码；auto=自动探测（默认 auto）")
    p.add_argument("--ignore-case", action="store_true", help="忽略大小写统计")
    p.add_argument("--min-len", type=int, default=0, help="只统计长度 >= N 的行（默认 0，不过滤）")
    args = p.parse_args(argv)

    path = args.file
    if not os.path.isfile(path):
        print(f"错误：文件不存在 {path}", file=sys.stderr)
        return 2

    enc = args.encoding
    if enc == "auto":
        enc = detect_encoding(path)

    counts: Counter = Counter()
    total_lines = 0
    try:
        with open(path, "r", encoding=enc, errors="strict") as f:
            for raw in f:
                total_lines += 1
                line = raw.rstrip("\r\n")
                if len(line) < args.min_len:
                    continue
                if args.ignore_case:
                    line = line.casefold()
                counts[line] += 1
    except UnicodeDecodeError as e:
        print(f"错误：用 {enc} 解码失败：{e}", file=sys.stderr)
        print("可尝试：--encoding gbk 或 --encoding latin-1", file=sys.stderr)
        return 2
    except (OSError, LookupError) as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2

    counted = sum(counts.values())
    dup_kinds = sum(1 for c in counts.values() if c > 1)
    redundant = sum(c - 1 for c in counts.values() if c > 1)
    rate = redundant / counted * 100 if counted else 0.0

    print(f"文件: {os.path.abspath(path)}")
    print(f"大小: {human_size(os.path.getsize(path))}  编码: {enc}")
    extra = (
        f"（--min-len {args.min_len} 过滤 {total_lines - counted} 行）"
        if counted != total_lines
        else ""
    )
    print(f"总行数: {total_lines}  计入统计: {counted}{extra}")
    print(f"唯一行数: {len(counts)}  重复行种数: {dup_kinds}  冗余行数: {redundant}")
    print(f"整体重复率: {rate:.2f}%（冗余行数 / 计入统计的行数）")

    if counts:
        print(f"\nTop {min(args.top, len(counts))} 重复行:")
        for i, (line, c) in enumerate(counts.most_common(args.top), 1):
            show = line if len(line) <= 80 else line[:77] + "..."
            show = show.replace("\t", "\\t")
            print(f"  {i:>3}. x{c:<6} ({c / counted * 100:5.2f}%)  {show!r}")
    else:
        print("\n（没有可统计的行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
