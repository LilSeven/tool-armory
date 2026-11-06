#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""竖排标点转换（vertical-punct-convert）

把横排标点转成竖排形式（如 （→︵、…→︙、—→︱、─→│、。→︒），
或用 --reverse 转回横排（输出全角形式，如 ︵→（、︒→。），用于竖排
版式文本。映射取自 unicodedata 中 U+FE30–U+FE48 的 <vertical> 分解
标签，并补充 U+2500/2501 制表线与 ASCII/全角同形括号的扩展映射。

用法：
    python -I vertical-punct-convert.py <输入文件> [-o 输出文件] [选项]
    python -I vertical-punct-convert.py --text "（中文）…—─《书》"
    python -I vertical-punct-convert.py 竖排.txt --reverse
    python -I vertical-punct-convert.py --list         # 打印映射表
    python -I vertical-punct-convert.py --self-test    # 运行内置自测

选项：
    -o, --output FILE   结果写入文件（缺省打印到标准输出）
    --text TEXT         直接处理命令行文本
    --reverse           竖排形式 → 横排形式（输出全角标点）
    --stats             统计被转换的标点个数
    --encoding ENC      输入文件编码（默认 utf-8）
    --list              列出映射表后退出
    --self-test         运行内置自测并退出

示例：
    python -I vertical-punct-convert.py h.txt -o v.txt --stats
    python -I vertical-punct-convert.py v.txt --reverse -o h.txt
"""

import argparse
import sys
import unicodedata
from collections import Counter

VERT_RANGE = range(0xFE00, 0xFE50)
FW_START, FW_END = 0xFF01, 0xFF5E
FW_OFFSET = 0xFEE0
# <vertical> 标签之外的手工补充（横 → 竖）
EXTRA_H2V = {
    0x2026: 0xFE19,  # … → ︙（UNICODE 已有标签，setdefault 兜底）
    0x2500: 0x2502,  # ─ → │（制表横线转竖线）
    0x2501: 0x2503,  # ━ → ┃
}


def build_h2v():
    """横排 → 竖排映射（含 ASCII/全角同形扩展）。"""
    h2v = {}
    for cp in VERT_RANGE:
        dec = unicodedata.decomposition(chr(cp))
        if not dec.startswith("<vertical> "):
            continue
        try:
            src = int(dec.split()[1], 16)
        except (IndexError, ValueError):
            continue
        h2v[src] = cp
    for src, dst in EXTRA_H2V.items():
        h2v.setdefault(src, dst)
    # 同形扩展：ASCII 与全角括号/标点指向同一竖排形式
    for src, dst in list(h2v.items()):
        if FW_START <= src <= FW_END:
            h2v.setdefault(src - FW_OFFSET, dst)
        elif 0x21 <= src <= 0x7E:
            h2v.setdefault(src + FW_OFFSET, dst)
    return h2v


def build_v2h(h2v):
    """竖排 → 横排映射；同形来源优先取全角形式。"""
    v2h = {}
    for src in sorted(h2v):
        dst = h2v[src]
        prefer = FW_START <= src <= FW_END
        if dst not in v2h or prefer:
            v2h[dst] = src
    return v2h


def transform(text, table):
    return text.translate(str.maketrans(table))


def count_changed(text, table):
    return sum(1 for ch in text if ord(ch) in table)


def format_cp(cp):
    return "U+{:04X}".format(cp)


def show_list(table):
    for src in sorted(table):
        dst = table[src]
        print("{} {!r} -> {} {!r}".format(format_cp(src), chr(src),
                                          format_cp(dst), chr(dst)))


def read_text(path, encoding):
    with open(path, "r", encoding=encoding, newline="") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def self_test():
    h2v = build_h2v()
    v2h = build_v2h(h2v)
    # 关键映射（均经本机 unicodedata 实测）
    assert h2v.get(0xFF08) == 0xFE35, h2v.get(0xFF08)   # （ → ︵
    assert h2v.get(0x0028) == 0xFE35                    # ( → ︵
    assert h2v.get(0x2026) == 0xFE19                    # … → ︙
    assert h2v.get(0x2014) == 0xFE31                    # — → ︱
    assert h2v.get(0x2500) == 0x2502                    # ─ → │
    assert h2v.get(0x3001) == 0xFE11                    # 、 → ︐
    assert h2v.get(0x3002) == 0xFE12                    # 。 → ︒
    # 全角/CJK 来源正排 + 逆排完整往返
    src = "（中文）《书》〔注〕【重点】…—─、。！？：［b］"
    vert = transform(src, h2v)
    assert "︵" in vert and "︙" in vert and "︱" in vert and "│" in vert
    assert transform(vert, v2h) == src, (vert, transform(vert, v2h))
    # ASCII 括号同样可转竖排
    assert transform("(a)", h2v) == "︵a︶"
    print("vertical-punct-convert 自测通过：正排 {} 项 / 逆排 {} 项，往返一致".format(
        len(h2v), len(v2h)))
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="横排标点 ↔ 竖排标点转换")
    parser.add_argument("input", nargs="?", help="输入文件（或配合 --text 使用）")
    parser.add_argument("-o", "--output", help="输出文件（缺省打印到标准输出）")
    parser.add_argument("--text", help="直接处理命令行文本")
    parser.add_argument("--reverse", action="store_true", help="竖排转回横排（输出全角）")
    parser.add_argument("--stats", action="store_true", help="统计被转换的标点个数")
    parser.add_argument("--encoding", default="utf-8", help="输入文件编码（默认 utf-8）")
    parser.add_argument("--list", action="store_true", help="列出映射表后退出")
    parser.add_argument("--self-test", action="store_true", help="运行内置自测后退出")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    h2v = build_h2v()
    table = build_v2h(h2v) if args.reverse else h2v
    if args.list:
        show_list(table)
        return 0

    if args.text is not None:
        text = args.text
    elif args.input:
        try:
            text = read_text(args.input, args.encoding)
        except (OSError, UnicodeError) as e:
            print("读取失败: {}".format(e), file=sys.stderr)
            return 1
    else:
        parser.error("请提供输入文件，或使用 --text 传入文本")
        return 2

    result = transform(text, table)
    if args.stats:
        print("字符总数: {}，转换标点: {} 个".format(len(text), count_changed(text, table)),
              file=sys.stderr)
    if args.output:
        try:
            write_text(args.output, result)
        except OSError as e:
            print("写入失败: {}".format(e), file=sys.stderr)
            return 1
        print("已写入: {}".format(args.output))
    else:
        sys.stdout.write(result)
        if not result.endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
