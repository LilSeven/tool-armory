#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""捕获组导出器（regex-harvest）：对文本跑带命名捕获组的正则，
把每组匹配结果导出为 CSV 或 JSONL。

用法:
    python -I regex-harvest.py -f log.txt -p "(?P<date>[\\d-]+) (?P<level>\\w+) (?P<msg>.*)" -o out.csv
    python -I regex-harvest.py -f log.txt -p "(?P<ip>\\d+\\.\\d+\\.\\d+\\.\\d+)" --format jsonl

说明:
    - 必须使用命名捕获组 (?P<name>...)；无命名组时报错退出。
    - CSV 首行为组名表头；未参与的组写空字符串；JSONL 中未参与的组为 null。
    - 默认逐行 search；加 --all 提取每行全部匹配。

只使用 Python 标准库（re / argparse / csv / json）。
"""
import argparse
import csv
import json
import re
import sys


def main():
    ap = argparse.ArgumentParser(description="提取命名捕获组结果并导出 CSV/JSONL")
    ap.add_argument("-f", "--file", required=True, help="输入文本文件（UTF-8）")
    ap.add_argument("-p", "--pattern", required=True, help="带命名捕获组的正则")
    ap.add_argument("-o", "--output", default="-", help="输出文件路径，缺省打印到 stdout")
    ap.add_argument("--format", choices=["csv", "jsonl"], default="csv", help="输出格式，默认 csv")
    ap.add_argument("-e", "--encoding", default="utf-8", help="输入编码，默认 utf-8")
    ap.add_argument("--all", action="store_true", help="提取每行的全部匹配（默认每行只取第一个）")
    args = ap.parse_args()

    try:
        pattern = re.compile(args.pattern)
    except re.error as e:
        print("正则编译失败: %s" % e, file=sys.stderr)
        return 2

    groupnames = [g for g in pattern.groupindex.keys()]
    if not groupnames:
        print("错误：正则中没有任何命名捕获组，请使用 (?P<名字>...) 形式。", file=sys.stderr)
        return 2

    try:
        with open(args.file, "r", encoding=args.encoding, errors="replace") as f:
            lines = f.read().splitlines()
    except OSError as e:
        print("无法读取文件: %s" % e, file=sys.stderr)
        return 2

    rows = []
    for no, line in enumerate(lines, 1):
        it = pattern.finditer(line) if args.all else iter(
            [m] if (m := pattern.search(line)) else [])
        for m in it:
            row = {"_line": no}
            for name in groupnames:
                row[name] = m.group(name)
            rows.append(row)

    out_stream = sys.stdout if args.output == "-" else open(
        args.output, "w", encoding="utf-8-sig" if args.format == "csv" else "utf-8", newline="")
    try:
        if args.format == "csv":
            writer = csv.DictWriter(out_stream, fieldnames=["_line"] + groupnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
        else:
            for row in rows:
                out_stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    finally:
        if out_stream is not sys.stdout:
            out_stream.close()

    dest = "stdout" if args.output == "-" else args.output
    print("提取 %d 条匹配记录（组: %s），已输出到 %s" % (len(rows), ", ".join(groupnames), dest),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
