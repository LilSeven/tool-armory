#!/usr/bin/env python3
"""JSONL 合并：把多个 JSON Lines 文件合并为一个，逐行校验并跳过报告坏行。

逐行用 json.loads 校验每个输入文件，坏行（非合法 JSON）跳过并打到 stderr，
合法行原样写入输出（保留原始文本，不重排键）。

用法:
    python merge-jsonl.py a.jsonl b.jsonl -o merged.jsonl
    python merge-jsonl.py a.jsonl -o merged.jsonl --strict   # 遇坏行直接报错退出

参数:
    inputs       输入 JSONL 文件（至少一个）
    -o, --output 输出文件（默认 stdout）
    --strict     遇到坏行时以非零码退出而非跳过
    --encoding   文件编码，默认 utf-8

示例:
    python merge-jsonl.py logs/*.jsonl -o all.jsonl
"""
import argparse
import json
import os
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(description="合并 JSON Lines 文件，校验并跳过坏行")
    ap.add_argument("inputs", nargs="+", help="输入 JSONL 文件")
    ap.add_argument("-o", "--output", help="输出文件，缺省打印到 stdout")
    ap.add_argument("--strict", action="store_true", help="遇坏行报错退出")
    ap.add_argument("--encoding", default="utf-8", help="文件编码（默认 utf-8）")
    args = ap.parse_args(argv)

    total = bad = 0
    bad_lines = []

    def write(line, out):
        out.write(line if line.endswith("\n") else line + "\n")

    out = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    try:
        for path in args.inputs:
            if not os.path.isfile(path):
                print(f"警告: 跳过不存在的文件 {path}", file=sys.stderr)
                continue
            with open(path, encoding=args.encoding) as f:
                for i, line in enumerate(f, 1):
                    s = line.strip()
                    if not s:
                        continue
                    total += 1
                    try:
                        json.loads(s)
                    except json.JSONDecodeError as e:
                        bad += 1
                        bad_lines.append(f"{path}:{i}: {e}")
                        if args.strict:
                            print(f"严格模式: {path}:{i}: {e}", file=sys.stderr)
                            return 1
                        continue
                    write(line, out)
    finally:
        if args.output:
            out.close()

    for b in bad_lines[:10]:
        print(f"坏行(已跳过): {b}", file=sys.stderr)
    if len(bad_lines) > 10:
        print(f"... 共 {len(bad_lines)} 个坏行", file=sys.stderr)
    print(f"共 {total} 行，合法 {total - bad}，坏行 {bad}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
