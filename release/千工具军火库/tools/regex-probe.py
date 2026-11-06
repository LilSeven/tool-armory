#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""正则批量验证器（regex-probe）：给定正则与样本文件，逐行标注命中/未命中，
输出命中数与首尾匹配位置报告。

用法:
    python -I regex-probe.py -p "^\\d+$" -f sample.txt
    python -I regex-probe.py -p "\\w+@\\w+\\.(com|cn)" -f sample.txt --show-positions
    python -I regex-probe.py -p "\\d+" -f sample.txt -e gbk   （非 UTF-8 文件用 -e 指定编码）

输出:
    - 每行前缀 [HIT]/[MISS] 与行号
    - 末尾汇总：总行数、命中数、未命中数
    - --show-positions：打印每行首个与最后一个匹配的起止位置（1 基列号）

只使用 Python 标准库（re / argparse / io）。
"""
import argparse
import re
import sys


def line_report(pattern: re.Pattern, line: str) -> str:
    """返回该行的首尾匹配位置描述。"""
    matches = list(pattern.finditer(line))
    if not matches:
        return "无匹配"
    first = matches[0]
    last = matches[-1]
    def pos(m):
        return "%d-%d (%r)" % (m.start() + 1, m.end(), m.group(0))
    if first is last:
        return "唯一匹配 " + pos(first)
    return "首个 " + pos(first) + "；末个 " + pos(last)


def main():
    ap = argparse.ArgumentParser(description="逐行验证文件内容是否命中正则")
    ap.add_argument("-p", "--pattern", required=True, help="正则表达式")
    ap.add_argument("-f", "--file", required=True, help="样本文件路径（UTF-8）")
    ap.add_argument("-e", "--encoding", default="utf-8", help="文件编码，默认 utf-8")
    ap.add_argument("-i", "--ignore-case", action="store_true", help="忽略大小写")
    ap.add_argument("--show-positions", action="store_true", help="显示每行首尾匹配位置")
    ap.add_argument("--quiet", action="store_true", help="只输出汇总，不逐行标注")
    args = ap.parse_args()

    flags = re.IGNORECASE if args.ignore_case else 0
    try:
        pattern = re.compile(args.pattern, flags)
    except re.error as e:
        print("正则编译失败: %s" % e, file=sys.stderr)
        return 2

    try:
        with open(args.file, "r", encoding=args.encoding, errors="replace") as f:
            lines = f.read().splitlines()
    except (OSError, LookupError) as e:
        print("无法读取文件（%s）: %s" % (
            "未知编码" if isinstance(e, LookupError) else "IO 错误", e), file=sys.stderr)
        return 2

    total = len(lines)
    hits = 0
    for no, line in enumerate(lines, 1):
        matched = pattern.search(line) is not None
        if matched:
            hits += 1
        if not args.quiet:
            tag = "[HIT] " if matched else "[MISS]"
            extra = ""
            if args.show_positions and matched:
                extra = "  | " + line_report(pattern, line)
            print("%s第 %d 行: %s%s" % (tag, no, line, extra))

    print("-" * 40)
    print("总行数: %d  命中: %d  未命中: %d" % (total, hits, total - hits))
    if total:
        print("命中率: %.1f%%" % (100.0 * hits / total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
