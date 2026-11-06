#!/usr/bin/env python3
"""JSONL 转 CSV：合并 JSONL 各对象的全部键为列，把行式 JSON 转成 CSV 表格。

嵌套对象/数组会先用点路径展平 (a.b.0) 再作为列值，标量直接 json 序列化。

用法:
    python jsonl2csv.py input.jsonl                # 输出到 stdout
    python jsonl2csv.py input.jsonl -o out.csv     # 输出到文件
    python jsonl2csv.py input.jsonl --no-flatten   # 嵌套值整体 JSON 序列化

示例命令:
    python jsonl2csv.py users.csv.jsonl
    cat data.jsonl | python jsonl2csv.py -
"""
import argparse
import csv
import json
import sys


def flatten(obj, prefix="", sep="."):
    """把嵌套 dict/list 展平为点路径键值对。"""
    flat = {}
    if isinstance(obj, dict):
        items = obj.items()
    elif isinstance(obj, list):
        items = [(str(i), v) for i, v in enumerate(obj)]
    else:
        return {prefix: obj} if prefix else {}
    for k, v in items:
        key = f"{prefix}{sep}{k}" if prefix else str(k)
        if isinstance(v, (dict, list)) and v:
            flat.update(flatten(v, key, sep))
        else:
            flat[key] = v
    return flat


def cell(value):
    """把值转成 CSV 单元格文本；容器值 JSON 序列化。"""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def convert(objects, no_flatten=False):
    """输入对象列表，返回 (列名列表, 行列表)。"""
    rows = []
    columns = []
    seen_cols = set()
    for obj in objects:
        if not isinstance(obj, dict):
            obj = {"value": obj}
        flat = obj if no_flatten else flatten(obj)
        for k in flat:
            if k not in seen_cols:
                seen_cols.add(k)
                columns.append(k)
        rows.append(flat)
    ordered = [[row.get(c, "") for c in columns] for row in rows]
    return columns, [[cell(v) for v in r] for r in ordered]


def main(argv=None):
    ap = argparse.ArgumentParser(description="JSONL 合并所有键转 CSV 表格")
    ap.add_argument("input", help="JSONL 文件路径，'-' 表示 stdin")
    ap.add_argument("-o", "--output", help="输出 CSV 路径，缺省 stdout")
    ap.add_argument("--no-flatten", action="store_true", help="嵌套值不展平，整体 JSON 序列化")
    ap.add_argument("--encoding", default="utf-8", help="输入编码 (默认 utf-8)")
    args = ap.parse_args(argv)

    objects = []
    src = sys.stdin if args.input == "-" else open(args.input, encoding=args.encoding)
    try:
        for lineno, line in enumerate(src, 1):
            line = line.strip()
            if not line:
                continue
            try:
                objects.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"jsonl2csv: 第 {lineno} 行 JSON 解析失败: {e}", file=sys.stderr)
                return 1
    finally:
        if args.input != "-":
            src.close()

    columns, rows = convert(objects, no_flatten=args.no_flatten)
    out = open(args.output, "w", encoding="utf-8-sig", newline="") if args.output else sys.stdout
    try:
        w = csv.writer(out)
        w.writerow(columns)
        w.writerows(rows)
    finally:
        if args.output:
            out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
