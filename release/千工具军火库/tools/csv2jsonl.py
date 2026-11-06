#!/usr/bin/env python3
"""CSV 转 JSONL：把 CSV 每行转为一个 JSON 对象，支持自动数字/布尔类型推断。

用法:
    python csv2jsonl.py input.csv                # 输出到 stdout
    python csv2jsonl.py input.csv -o out.jsonl   # 输出到文件
    python csv2jsonl.py input.csv --no-infer     # 全部保留字符串，不推断类型

示例命令:
    python csv2jsonl.py people.csv
    cat people.csv | python csv2jsonl.py -      # 从 stdin 读

推断规则: "true"/"false"(不区分大小写) -> bool; 整数 -> int;
浮点数 -> float; 空串 -> "" (不转 null，除非 --null-empty)。
首行为表头，作为各对象的键；多余列以 header_N 命名。
"""
import argparse
import csv
import json
import sys


def infer(text: str, null_empty: bool = False):
    """把字符串推断为 int/float/bool，失败则原样返回。"""
    s = text.strip()
    if s == "":
        return None if null_empty else ""
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "none"):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return text


def convert(rows, no_infer=False, null_empty=False):
    """rows: 可迭代的 list[list[str]]，首行为表头。返回对象列表。"""
    objects = []
    it = iter(rows)
    try:
        header = next(it)
    except StopIteration:
        return objects
    header = [h.strip() if h.strip() else f"column_{i+1}"
              for i, h in enumerate(header)]
    seen = {}
    for i, h in enumerate(header):  # 去重表头
        if h in seen:
            seen[h] += 1
            header[i] = f"{h}_{seen[h]}"
        else:
            seen[h] = 0
    for row in it:
        if not row or (len(row) == 1 and row[0] == ""):
            continue
        obj = {}
        for i in range(max(len(header), len(row))):
            key = header[i] if i < len(header) else f"column_{i+1}"
            val = row[i] if i < len(row) else ""
            obj[key] = val if no_infer else infer(val, null_empty)
        objects.append(obj)
    return objects


def main(argv=None):
    ap = argparse.ArgumentParser(description="CSV 每行转一个 JSON 对象 (JSONL)")
    ap.add_argument("input", help="CSV 文件路径，'-' 表示 stdin")
    ap.add_argument("-o", "--output", help="输出文件路径，缺省 stdout")
    ap.add_argument("--no-infer", action="store_true", help="不推断类型")
    ap.add_argument("--null-empty", action="store_true", help="空串转 null")
    ap.add_argument("--encoding", default="utf-8-sig", help="输入编码 (默认 utf-8-sig)")
    args = ap.parse_args(argv)

    if args.input == "-":
        objects = convert(csv.reader(sys.stdin),
                          no_infer=args.no_infer, null_empty=args.null_empty)
    else:
        with open(args.input, newline="", encoding=args.encoding) as f:
            objects = convert(csv.reader(f),
                              no_infer=args.no_infer, null_empty=args.null_empty)
    out = open(args.output, "w", encoding="utf-8", newline="\n") if args.output else sys.stdout
    try:
        for obj in objects:
            out.write(json.dumps(obj, ensure_ascii=False) + "\n")
    finally:
        if args.output:
            out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
