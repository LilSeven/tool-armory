#!/usr/bin/env python3
r"""Markdown 表格转 CSV — 解析 Markdown 文档中的表格块并导出为 CSV 文件。

扫描 Markdown 文本中所有形如 | a | b | 的表格块，跳过 |---| 分隔行，
自动去除单元格内的转义（\| 还原为 |，<br> 还原为换行），写出为 CSV。
只使用 Python 标准库（re / csv / argparse）。

用法:
    python mdtable2csv.py input.md -o out.csv       # 第一个表格导出为 CSV
    python mdtable2csv.py input.md --all -o out.csv # 多个表格分别导出 out1.csv...
    python mdtable2csv.py -e "| a | b |\n| --- | --- |\n| 1 | 2 |" -o out.csv
                                                    # 内联输入（\n 解释为换行）

示例:
    $ python mdtable2csv.py -e "| 名 | 注 |\n| --- | --- |\n| x | a\\|b |" -o t.csv
    已导出 1 个表格 -> t.csv

注: -e 内联字符串中的 \n、\t、\r 会被解释为换行/制表/回车，\\ 表示字面反斜杠；
    文件输入不做任何转义解释。
"""

import argparse
import csv
import os
import re
import sys

# 一行看起来像表格行的：以 | 开头或包含 |，且内容非空
ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
# 分隔行：只有 | - : 与空白
SEP_RE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")


def unescape_inline(text):
    r"""解释 -e 内联字符串中的转义：\n→换行、\t→制表、\r→回车、\\→反斜杠。"""
    mapping = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\"}
    out = []
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text) and text[i + 1] in mapping:
            out.append(mapping[text[i + 1]])
            i += 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def unescape_cell(text):
    r"""还原单元格：\| -> |，<br> -> 换行。"""
    return text.replace(r"\|", "|").replace("<br>", "\n").strip()


def split_row(line):
    r"""把 '| a | b\|c |' 拆成 ['a', 'b|c']。"""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    # 按未被反斜杠转义的 | 分割
    cells, buf, esc = [], [], False
    for ch in line:
        if esc:
            buf.append("\\" + ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == "|":
            cells.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if esc:
        buf.append("\\")
    cells.append("".join(buf))
    return [unescape_cell(c) for c in cells]


def find_tables(md_text):
    """从 Markdown 文本中提取所有表格块，返回 [行列表] 的列表（已去分隔行）。"""
    tables, current = [], []
    for line in md_text.splitlines():
        if ROW_RE.match(line):
            if SEP_RE.match(line):
                continue  # 跳过对齐分隔行
            current.append(split_row(line))
        else:
            if current:
                tables.append(current)
                current = []
    if current:
        tables.append(current)
    return tables


def main(argv=None):
    parser = argparse.ArgumentParser(description="解析 Markdown 中的表格块并导出为 CSV")
    parser.add_argument("input", nargs="?", help="输入 Markdown 文件路径")
    parser.add_argument("-e", "--expr", help="内联 Markdown 字符串（\\n 解释为换行，与 input 二选一）")
    parser.add_argument("-o", "--output", required=True, help="输出 CSV 文件路径")
    parser.add_argument("--all", action="store_true", help="导出全部表格（文件名追加序号 out1.csv...）")
    parser.add_argument("--encoding", default="utf-8-sig", help="输出 CSV 编码（默认 utf-8-sig）")
    args = parser.parse_args(argv)

    if bool(args.input) == bool(args.expr):
        parser.error("必须且只能提供 input 文件或 -e 内联字符串之一")

    if args.expr:
        md_text = unescape_inline(args.expr)
    else:
        try:
            with open(args.input, "r", encoding="utf-8") as fh:
                md_text = fh.read()
        except OSError as exc:
            print(f"错误: 读取文件失败: {exc}", file=sys.stderr)
            return 1

    tables = find_tables(md_text)
    if not tables:
        print("错误: 未在输入中找到 Markdown 表格", file=sys.stderr)
        return 1

    outputs = [args.output]
    if args.all and len(tables) > 1:
        base, ext = os.path.splitext(args.output)
        outputs = [f"{base}{i + 1}{ext or '.csv'}" for i in range(len(tables))]

    for path, table in zip(outputs, tables):
        try:
            with open(path, "w", encoding=args.encoding, newline="") as fh:
                csv.writer(fh).writerows(table)
        except OSError as exc:
            print(f"错误: 写入 {path} 失败: {exc}", file=sys.stderr)
            return 1

    if len(outputs) == 1:
        msg = f"已导出 1 个表格 -> {args.output}"
        if len(tables) > 1:
            msg += f"（共发现 {len(tables)} 个，其余需 --all 才会导出）"
        print(msg)
    else:
        print(f"已导出 {len(tables)} 个表格 -> {outputs[0]} ...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
