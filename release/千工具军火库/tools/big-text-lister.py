#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大文本文件排行（big-text-lister）。

用途：
    在目录（含子目录）中按文件大小找出最大的若干个文本文件，逐一给出
    大小、行数与编码信息，用于快速定位日志膨胀源头。开头 64KB 内含 NUL
    字节的文件视为二进制并跳过。

用法：
    python -I big-text-lister.py <目录> [-k TOP]

示例（Git Bash / Windows）：
    python -I big-text-lister.py K:/logs -k 10

说明：
    * 编码探测顺序：UTF-8 BOM -> UTF-16 BOM -> 二进制(NUL) -> UTF-8 -> GBK -> latin-1 兜底；
    * 行数为流式统计文本行得出；UTF-16 文件需带 BOM 才能识别；
    * 探测基于开头 64KB 样本，极个别混合编码文件可能标注为 latin-1 兜底；
    * 退出码：0=成功；2=目录不存在。
"""

from __future__ import annotations

import argparse
import os
import sys


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


def probe_text(path: str):
    """返回 (encoding, is_text)。encoding 为 None 表示二进制文件。"""
    with open(path, "rb") as f:
        head = f.read(65536)
    if not head:
        return "utf-8", True
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", True
    if head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff"):
        return "utf-16", True
    if b"\x00" in head:
        return None, False
    # 截到最后一个换行处，避免多字节编码在样本边界被截断导致误判
    idx = head.rfind(b"\n")
    sample = head[: idx + 1] if idx != -1 else head
    for enc in ("utf-8", "gbk"):
        try:
            sample.decode(enc)
            return enc, True
        except UnicodeDecodeError:
            continue
    return "latin-1", True


def count_lines(path: str, encoding: str) -> int:
    n = 0
    with open(path, "r", encoding=encoding, errors="replace") as f:
        for _ in f:
            n += 1
    return n


def main(argv=None) -> int:
    _stdout_utf8()
    p = argparse.ArgumentParser(
        prog="big-text-lister", description="找出目录中最大的文本文件并列出行数与编码"
    )
    p.add_argument("directory", help="要扫描的目录")
    p.add_argument("-k", "--top", type=int, default=10, help="列出前 K 个最大的文本文件（默认 10）")
    args = p.parse_args(argv)

    root = args.directory
    if not os.path.isdir(root):
        print(f"错误：目录不存在 {root}", file=sys.stderr)
        return 2

    candidates = []
    scanned = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            scanned += 1
            candidates.append((size, full))
    candidates.sort(key=lambda t: (-t[0], t[1]))

    rows = []
    skipped_binary = 0
    for size, full in candidates:
        if len(rows) >= args.top:
            break
        try:
            enc, is_text = probe_text(full)
        except OSError as e:
            print(f"警告：无法读取 {full}: {e}", file=sys.stderr)
            continue
        if not is_text:
            skipped_binary += 1
            continue
        lines = count_lines(full, enc)
        rows.append((size, lines, enc, full.replace(os.sep, "/")))

    print(f"目录: {os.path.abspath(root)}")
    print(f"扫描文件总数: {scanned}  跳过二进制: {skipped_binary}  列出: {len(rows)}")
    if not rows:
        print("（未找到文本文件）")
        return 0
    print(f"\nTop {len(rows)} 大文本文件:")
    for i, (size, lines, enc, full) in enumerate(rows, 1):
        print(f"  {i:>3}. {human_size(size):>10}  {lines:>8} 行  {enc:<10} {full}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
