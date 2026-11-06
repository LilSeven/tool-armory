#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON 转 CSV：把 JSON 对象数组转成 CSV，自动收集所有键作表头。

嵌套字段用点路径展平（如 addr.city）；数组/对象字段默认序列化为 JSON 文本
（可用 --list-join 让数组用分隔符拼接）。--cols 可选择并排序输出列，
对象中缺失的键输出空单元格。只用 Python 标准库。

用法:
    python json2csv-flat.py data.json
    python json2csv-flat.py data.json -o out.csv
    cat data.json | python json2csv-flat.py -
    python json2csv-flat.py data.json --cols name,addr.city
    python json2csv-flat.py data.json --list-join ";"
    python json2csv-flat.py data.json --delimiter ";" --no-header --bom
"""

import argparse
import csv
import json
import sys


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


def flatten(obj, prefix=""):
    """把嵌套 dict 展平成 {点路径: 值}；空 dict 与 list 视为叶子。"""
    out = {}
    for k, v in obj.items():
        path = "%s.%s" % (prefix, k) if prefix else str(k)
        if isinstance(v, dict) and v:
            out.update(flatten(v, path))
        else:
            out[path] = v
    return out


def to_cell(value, list_join):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        if list_join is not None:
            return list_join.join("" if x is None else str(x) for x in value)
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def read_text(path):
    if path == "-":
        text = sys.stdin.read()
    else:
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                text = f.read()
        except OSError as e:
            raise SystemExit("错误: 无法读取 %s: %s" % (path, e))
    if text.startswith("\ufeff"):
        text = text[1:]
    return text


def main(argv=None):
    _setup_streams()

    parser = argparse.ArgumentParser(
        prog="json2csv-flat",
        description="JSON 对象数组 → CSV（自动收集键、点路径展平、--cols 选列）。")
    parser.add_argument("input", nargs="?", default="-",
                        help="输入 JSON 路径，'-' 或省略表示 stdin")
    parser.add_argument("-o", "--output", help="输出 CSV 路径（默认 stdout）")
    parser.add_argument("--cols", metavar="C1,C2",
                        help="逗号分隔的列名（点路径），选择并排序输出列")
    parser.add_argument("--list-join", metavar="SEP",
                        help="数组字段用 SEP 拼接（默认输出 JSON 文本）")
    parser.add_argument("--delimiter", default=",", help="字段分隔符，默认逗号")
    parser.add_argument("--no-header", action="store_true", help="不输出表头行")
    parser.add_argument("--bom", action="store_true",
                        help="写文件时加 UTF-8 BOM（便于 Excel 识别）")
    args = parser.parse_args(argv)

    try:
        data = json.loads(read_text(args.input))
    except ValueError as e:
        raise SystemExit("错误: JSON 解析失败: %s" % e)
    if not isinstance(data, list):
        raise SystemExit("错误: 顶层必须是 JSON 数组，收到 %s" % type(data).__name__)
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise SystemExit("错误: 第 %d 个元素不是 JSON 对象（是 %s）"
                             % (idx + 1, type(item).__name__))

    rows = [flatten(x) for x in data]
    headers, seen = [], set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                headers.append(k)

    if args.cols:
        cols = [c.strip() for c in args.cols.split(",") if c.strip()]
        if rows:
            unknown = [c for c in cols if c not in seen]
            if unknown:
                raise SystemExit("错误: --cols 引用了不存在的列: %s" % ", ".join(unknown))
        headers = cols

    out = None
    try:
        if args.output:
            out = open(args.output, "w",
                       encoding="utf-8-sig" if args.bom else "utf-8",
                       newline="")
        else:
            out = sys.stdout
        writer = csv.writer(out, delimiter=args.delimiter, lineterminator="\n")
        if not args.no_header and headers:
            writer.writerow(headers)
        for r in rows:
            writer.writerow([to_cell(r.get(c), args.list_join) for c in headers])
    except OSError as e:
        raise SystemExit("错误: 写入失败: %s" % e)
    finally:
        if args.output and out is not None:
            out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
