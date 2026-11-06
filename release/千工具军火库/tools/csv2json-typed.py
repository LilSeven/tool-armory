#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CSV 转 JSON：输出对象数组，自动推断数字 / 布尔 / null 类型。

推断规则（可用 --strings 关闭推断，全部保留原始字符串）:
    空单元格          -> null
    true / false      -> 布尔（大小写不敏感）
    整数 / 浮点数     -> 数字（支持科学计数法；1_000、Inf、NaN 等不视为数字）
    其他              -> 字符串

用法:
    python csv2json-typed.py data.csv
    python csv2json-typed.py data.csv -o out.json
    cat data.csv | python csv2json-typed.py -
    python csv2json-typed.py data.csv --strings
    python csv2json-typed.py data.csv --null "N/A,NULL"
    python csv2json-typed.py data.csv --delimiter ";" --compact
"""

import argparse
import csv
import json
import re
import sys

INT_RE = re.compile(r"^[+-]?\d+$")
FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")


def _setup_streams():
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


def infer(cell, nulls):
    """把单元格文本推断成 bool / int / float / None / str。"""
    t = cell.strip()
    if t == "" or t.lower() in nulls:
        return None
    if t.lower() == "true":
        return True
    if t.lower() == "false":
        return False
    if INT_RE.match(t):
        return int(t)
    if FLOAT_RE.match(t):
        return float(t)
    return cell


def read_rows(path, delimiter):
    if path == "-":
        rows = list(csv.reader(sys.stdin, delimiter=delimiter))
    else:
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f, delimiter=delimiter))
        except OSError as e:
            raise SystemExit("错误: 无法读取 %s: %s" % (path, e))
    if rows and rows[0] and rows[0][0].startswith("\ufeff"):
        rows[0][0] = rows[0][0].lstrip("\ufeff")
    return rows


def main(argv=None):
    _setup_streams()

    parser = argparse.ArgumentParser(
        prog="csv2json-typed",
        description="CSV → JSON 数组（自动推断数字/布尔/null 类型）。")
    parser.add_argument("input", nargs="?", default="-",
                        help="输入 CSV 路径，'-' 或省略表示 stdin")
    parser.add_argument("-o", "--output", help="输出 JSON 路径（默认 stdout）")
    parser.add_argument("--strings", action="store_true",
                        help="不做类型推断，全部保留为字符串")
    parser.add_argument("--null", default="", metavar="TOKENS",
                        help="逗号分隔的额外 null 标记（大小写不敏感），如 \"N/A,NULL\"")
    parser.add_argument("--delimiter", default=",", help="字段分隔符，默认逗号")
    parser.add_argument("--compact", action="store_true", help="单行输出 JSON")
    args = parser.parse_args(argv)

    nulls = {t.strip().lower() for t in args.null.split(",") if t.strip()}
    rows = read_rows(args.input, args.delimiter)
    data = []
    if rows:
        header = rows[0]
        for row in rows[1:]:
            if not row:  # 跳过空行
                continue
            rec = {}
            for j, cell in enumerate(row):
                key = header[j] if j < len(header) else "extra_%d" % (j + 1)
                rec[key] = cell if args.strings else infer(cell, nulls)
            data.append(rec)

    text = json.dumps(data, ensure_ascii=False,
                      indent=None if args.compact else 2)
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8", newline="\n") as f:
                f.write(text + "\n")
        except OSError as e:
            raise SystemExit("错误: 无法写入 %s: %s" % (args.output, e))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
