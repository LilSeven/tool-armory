#!/usr/bin/env python3
"""模板批量渲染：用 string.Template 把 CSV/JSONL 每行数据填入模板批量生成文本。

数据源支持 CSV（首行为表头，列名即变量名）与 JSONL（每行一个 JSON 对象）。
模板使用 string.Template 语法：$name 或 ${name}，可用 $name 或 ${name} 引用列。

用法:
    python batch-render.py data.csv template.txt
    python batch-render.py data.jsonl template.txt -o out/
    python batch-render.py data.csv template.txt -e utf-8 --strict

示例命令:
    python batch-render.py users.csv mail.tmpl -o mail/
    python batch-render.py rows.jsonl report.tmpl --strict
"""
import argparse
import csv
import io
import json
import os
import sys
from string import Template


def load_rows(path: str, encoding: str, delim: str) -> list:
    with open(path, "r", encoding=encoding, newline="") as f:
        if path.lower().endswith((".jsonl", ".ndjson")):
            rows = []
            for n, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    raise SystemExit(f"错误: 第 {n} 行不是合法 JSON: {e}")
                if not isinstance(obj, dict):
                    raise SystemExit(f"错误: 第 {n} 行不是 JSON 对象")
                rows.append(obj)
            return rows
        reader = csv.DictReader(io.StringIO(f.read()), delimiter=delim)
        return [{k: ("" if v is None else v) for k, v in r.items() if k is not None}
                for r in reader]


def main() -> int:
    ap = argparse.ArgumentParser(description="用 string.Template 批量渲染 CSV/JSONL 数据")
    ap.add_argument("data", help="数据文件（.csv 或 .jsonl，按扩展名识别）")
    ap.add_argument("template", help="模板文件（string.Template 语法）")
    ap.add_argument("-o", "--outdir", default=None,
                    help="输出目录；每行渲染结果写到 <outdir>/out-N.txt（缺省打印到 stdout，行间用 --- 分隔）")
    ap.add_argument("-e", "--encoding", default="utf-8", help="文件编码（默认 utf-8）")
    ap.add_argument("-d", "--delim", default=",", help="CSV 分隔符（默认逗号）")
    ap.add_argument("--strict", action="store_true",
                    help="模板中出现数据缺失的变量时报错（string.Template 的 strict 模式）")
    args = ap.parse_args()

    try:
        with open(args.template, "r", encoding=args.encoding) as f:
            tmpl = Template(f.read())
        rows = load_rows(args.data, args.encoding, args.delim)
    except OSError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    if not rows:
        print("(数据为空，无输出)", file=sys.stderr)
        return 0

    outputs = []
    cur = 0
    try:
        for i, row in enumerate(rows, 1):
            cur = i
            outputs.append((i, tmpl.substitute(row) if args.strict else tmpl.safe_substitute(row)))
    except KeyError as e:
        print(f"错误: 第 {cur} 行数据缺少变量 {e}（--strict 模式）",
              file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"错误: 模板占位符不合法: {e}", file=sys.stderr)
        return 1

    if args.outdir:
        os.makedirs(args.outdir, exist_ok=True)
        for i, text in outputs:
            outpath = os.path.join(args.outdir, f"out-{i}.txt")
            with open(outpath, "w", encoding=args.encoding, newline="") as f:
                f.write(text)
                if not text.endswith("\n"):
                    f.write("\n")
        print(f"已渲染 {len(outputs)} 个文件到 {args.outdir}/")
    else:
        for i, text in outputs:
            print(text)
            if i != len(outputs):
                print("---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
