#!/usr/bin/env python3
"""Markdown 表格转 CSV —— 解析 Markdown 文档中的表格行，还原为标准 CSV 文件。

用法:
    python md-table-to-csv.py input.md -o output.csv
    python md-table-to-csv.py input.md            # 缺省输出到 stdout
    python md-table-to-csv.py -                   # 从 stdin 读取

示例命令:
    python md-table-to-csv.py notes.md -o table.csv
    type README.md | python md-table-to-csv.py - -o readme_tables.csv

规则:
    - 识别以 '|' 定界的表格行，跳过对齐分隔行（如 | --- | :---: |）。
    - 单元格内 \\| 转义的字面竖线会被还原为 '|'。
    - 文档中有多个表格时，各表之间在 CSV 中以一个空行分隔。
    - 列数不一致时按最长的行补空列。
"""
import argparse
import csv
import re
import sys

SEP_CELL = re.compile(r"^:?-+:?$")


def _setup_streams():
    """强制 stdin/stdout 为 UTF-8，避免 python -I 下管道按 GBK 解码产生孤立代理。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", newline="")
        except Exception:
            pass
    try:
        if sys.stdin is not None:
            sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass


def split_row(line):
    """把一行 Markdown 表格行切分为单元格列表，还原 \\| 转义。"""
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    cells = re.split(r"(?<!\\)\|", line)
    return [c.replace("\\|", "|").strip() for c in cells]


def is_separator(cells):
    return bool(cells) and all(SEP_CELL.match(c) for c in cells if c != "") and any(
        SEP_CELL.match(c) for c in cells
    )


def extract_tables(text):
    """从文本中提取所有表格，返回 [ [row, ...], ... ]（每个表一组行）。"""
    tables = []
    current = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("|") and "|" in line[1:]:
            cells = split_row(line)
            if is_separator(cells):
                continue
            current.append(cells)
        else:
            if current:
                tables.append(current)
                current = []
    if current:
        tables.append(current)
    return tables


def main(argv=None):
    ap = argparse.ArgumentParser(description="解析 Markdown 表格行并输出标准 CSV")
    ap.add_argument("input", help="输入 .md 文件路径，'-' 表示 stdin")
    ap.add_argument("-o", "--output", help="输出 CSV 路径，缺省 stdout")
    ap.add_argument("-d", "--delimiter", default=",", help="CSV 分隔符（默认 ,）")
    args = ap.parse_args(argv)

    _setup_streams()

    if args.input == "-":
        text = sys.stdin.read()
    else:
        try:
            with open(args.input, "r", encoding="utf-8-sig") as f:
                text = f.read()
        except OSError as e:
            print(f"错误: 无法读取输入文件: {e}", file=sys.stderr)
            return 2

    tables = extract_tables(text)
    if not tables:
        print("提示: 未在文档中找到 Markdown 表格", file=sys.stderr)

    out = open(args.output, "w", encoding="utf-8", newline="") if args.output else sys.stdout
    try:
        writer = csv.writer(out, delimiter=args.delimiter, lineterminator="\n")
        width = max((len(r) for t in tables for r in t), default=0)
        for i, table in enumerate(tables):
            if i:
                writer.writerow([])  # 表与表之间空行分隔
            for row in table:
                writer.writerow(row + [""] * (width - len(row)))
    finally:
        if args.output:
            out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
