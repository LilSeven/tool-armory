#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""行数统计器（line-count-stats）

统计目录下文本文件的 行数 / 最长行长度 / 空行数与空行率，并给出目录级汇总报表。
二进制文件（前 8KB 含 NUL 字节）会被跳过并计入汇总的 binary_skipped。
行按换行符切分：文件末尾不带换行的残行也计为一行；最长行按解码后的字符数计
（UTF-8 解码失败时用替换字符继续统计，并在明细中标记 [non-utf8]）。

用法:
    python line-count-stats.py <目录或文件> [选项]

选项:
    --top N     明细最多显示前 N 个文件（按行数降序），0=全部（默认 20）
    --json      以 JSON 格式输出
    --hidden    包含以 . 开头的隐藏文件/目录

示例:
    python line-count-stats.py ./src
    python line-count-stats.py ./src --top 5 --json

仅使用 Python 标准库。
退出码: 0=扫描完成; 1=路径不存在; 2=参数错误。
"""

import argparse
import json
import os
import sys


def analyze_file(path):
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        return {"path": path, "kind": "error", "error": str(exc)}
    if not data:
        return {"path": path, "kind": "empty", "lines": 0, "longest": 0,
                "blank": 0, "blank_rate": 0.0, "utf8": True}
    if b"\x00" in data[:8192]:
        return {"path": path, "kind": "binary"}
    try:
        text = data.decode("utf-8")
        utf8 = True
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
        utf8 = False
    if data.endswith(b"\n"):
        parts = text[:-1].split("\n")
    else:
        parts = text.split("\n")
    lines = len(parts)
    longest = 0
    blank = 0
    for raw in parts:
        line = raw[:-1] if raw.endswith("\r") else raw
        if len(line) > longest:
            longest = len(line)
        if not line.strip():
            blank += 1
    return {
        "path": path, "kind": "text", "lines": lines, "longest": longest,
        "blank": blank, "blank_rate": (blank / lines) if lines else 0.0,
        "utf8": utf8,
    }


def iter_files(root, include_hidden):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        if include_hidden:
            dirnames[:] = sorted(dirnames)
            names = sorted(filenames)
        else:
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            names = sorted(f for f in filenames if not f.startswith("."))
        for name in names:
            yield os.path.join(dirpath, name)


def trunc(s, n):
    return s if len(s) <= n else "..." + s[-(n - 3):]


def display(path, root):
    try:
        rel = os.path.relpath(path, root)
    except ValueError:
        return path
    return path if rel.startswith("..") else rel


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="line-count-stats",
        description="统计文本文件行数、最长行与空行率，并给出目录级汇总报表。",
    )
    parser.add_argument("path", help="要统计的目录（或单个文件）")
    parser.add_argument("--top", type=int, default=20,
                        help="明细最多显示前 N 个文件（按行数降序），0=全部（默认 20）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--hidden", action="store_true", help="包含隐藏文件/目录")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not os.path.exists(args.path):
        print("错误: 路径不存在: %s" % args.path, file=sys.stderr)
        return 1

    results = [analyze_file(p) for p in iter_files(args.path, args.hidden)]
    text_rows = [r for r in results if r["kind"] == "text"]
    empty_rows = [r for r in results if r["kind"] == "empty"]
    binary_rows = [r for r in results if r["kind"] == "binary"]
    error_rows = [r for r in results if r["kind"] == "error"]
    text_rows.sort(key=lambda r: (-r["lines"], r["path"]))

    countable = text_rows + empty_rows  # 二进制/读取失败的文件不计行数
    total_lines = sum(r["lines"] for r in countable)
    total_blank = sum(r["blank"] for r in countable)
    overall_blank_rate = (total_blank / total_lines) if total_lines else 0.0
    avg = (total_lines / len(text_rows)) if text_rows else 0.0
    max_row = max(text_rows, key=lambda r: r["lines"]) if text_rows else None
    longest_row = max(text_rows, key=lambda r: r["longest"]) if text_rows else None
    decode_issues = sum(1 for r in text_rows if not r["utf8"])

    if args.json:
        payload = {
            "root": args.path,
            "summary": {
                "text_files": len(text_rows),
                "empty_files": len(empty_rows),
                "binary_skipped": len(binary_rows),
                "read_errors": len(error_rows),
                "decode_issues": decode_issues,
                "total_lines": total_lines,
                "total_blank": total_blank,
                "overall_blank_rate": overall_blank_rate,
                "avg_lines_per_file": avg,
                "max_lines": max_row["lines"] if max_row else 0,
                "max_lines_file": max_row["path"] if max_row else None,
                "global_longest_line": longest_row["longest"] if longest_row else 0,
                "global_longest_file": longest_row["path"] if longest_row else None,
            },
            "files": results,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("扫描目标: %s   文本 %d | 空文件 %d | 跳过二进制 %d | 读取失败 %d" % (
        args.path, len(text_rows), len(empty_rows), len(binary_rows), len(error_rows)))
    if text_rows:
        print()
        print("文件明细（按行数降序，最多显示 %s 个）:" % (args.top if args.top else "全部"))
        print("  %-42s %6s %6s %5s %8s" % ("文件", "行数", "最长行", "空行", "空行率"))
        shown = text_rows if args.top == 0 else text_rows[:args.top]
        for r in shown:
            mark = "" if r["utf8"] else " [non-utf8]"
            print("  %-42s %6d %6d %5d %7.1f%%%s" % (
                trunc(display(r["path"], args.path), 42),
                r["lines"], r["longest"], r["blank"], r["blank_rate"] * 100, mark))
        print()
        print("目录汇总:")
        print("  总行数 %d，总空行 %d，整体空行率 %.1f%%" % (
            total_lines, total_blank, overall_blank_rate * 100))
        print("  平均行数/文本文件: %.1f" % avg)
        if max_row:
            print("  单文件行数最多: %d 行 (%s)" % (
                max_row["lines"], display(max_row["path"], args.path)))
        if longest_row:
            print("  全局最长行: %d 字符 (%s)" % (
                longest_row["longest"], display(longest_row["path"], args.path)))
        if decode_issues:
            print("  注意: %d 个文件不是有效 UTF-8，已按替换字符统计" % decode_issues)
    else:
        print("没有可统计的文本文件。")
    for r in error_rows:
        print("  [读取失败] %s: %s" % (r["path"], r["error"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
