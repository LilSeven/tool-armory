#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""术语表强制替换：按用户词表对文本做最长优先的术语替换（stdin/文件 -> stdout/文件）。

词表为两列 CSV：术语,替换词（多余列忽略；--reverse 反向使用）。
同一位置命中多个术语时优先最长者（如词表含"软件"与"自由软件"，
文本"自由软件"只按"自由软件"整词替换，不会被先拆成"软件"）。
与简繁转换组合实现术语级地区化，例如：
  cat in.txt | python -I s2t-stream.py -d t | python -I term-enforce.py terms.csv > out.txt

示例命令：
  python -I term-enforce.py terms.csv input.txt -o output.txt --report
  cat input.txt | python -I term-enforce.py terms.csv > output.txt
  python -I term-enforce.py terms.csv --reverse < trad.txt > simp.txt
"""
import argparse
import csv
import re
import sys


def load_terms(path, reverse=False, case_insensitive=False):
    """读取两列 CSV 词表，返回 (pattern, lookup)。pattern 为最长优先的正则。"""
    lookup = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for lineno, row in enumerate(csv.reader(f), 1):
            if not row or len(row) < 2:
                if row and row[0].strip() in ("term", "简"):
                    continue  # 跳过常见表头
                if row and not row[0].strip():
                    continue
                print("警告：第 %d 行不足两列，已跳过" % lineno, file=sys.stderr)
                continue
            term, repl = row[0].strip(), row[1].strip()
            if not term:
                continue
            key = term.lower() if case_insensitive else term
            if key in lookup and lookup[key] != repl:
                print("警告：术语 %r 重复定义，保留后者" % term, file=sys.stderr)
            lookup[key] = repl
    if not lookup:
        return None, {}
    keys = sorted(lookup, key=len, reverse=True)  # 最长优先
    pattern = re.compile("|".join(re.escape(k) for k in keys),
                         re.IGNORECASE if case_insensitive else 0)
    return pattern, lookup


def enforce(text, pattern, lookup):
    """执行替换，返回 (新文本, 计数表)。pattern 为 None 时原样返回。"""
    if pattern is None:
        return text, {}
    counts = {}

    def _sub(m):
        key = m.group(0).lower() if pattern.flags & re.IGNORECASE else m.group(0)
        repl = lookup.get(key)
        if repl is None:  # 大小写不敏感但原始键未小写化的兜底
            repl = lookup.get(m.group(0), m.group(0))
        counts[key] = counts.get(key, 0) + 1
        return repl

    return pattern.sub(_sub, text), counts


def _read_text(paths):
    if paths:
        parts = []
        for p in paths:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                parts.append(f.read())
        return "".join(parts)
    return sys.stdin.read()


def main(argv=None):
    ap = argparse.ArgumentParser(description="按词表做最长优先的术语替换")
    ap.add_argument("terms", help="术语表 CSV（两列：术语,替换词）")
    ap.add_argument("inputs", nargs="*", help="输入文件（缺省读 stdin）")
    ap.add_argument("-o", "--output", help="输出文件（缺省写 stdout）")
    ap.add_argument("-r", "--reverse", action="store_true",
                    help="反向替换：把词表第二列内容替换回第一列")
    ap.add_argument("-i", "--ignore-case", action="store_true",
                    help="匹配时忽略大小写（主要影响 ASCII 术语）")
    ap.add_argument("--report", action="store_true",
                    help="在 stderr 打印每个术语的替换次数")
    args = ap.parse_args(argv)

    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace", newline="")

    pattern, lookup = load_terms(args.terms, args.reverse, args.ignore_case)
    if pattern is None:
        print("警告：词表为空，未做任何替换", file=sys.stderr)
    if args.reverse and lookup:
        lookup = {repl: term for term, repl in lookup.items()}
        keys = sorted(lookup, key=len, reverse=True)
        pattern = re.compile("|".join(re.escape(k) for k in keys),
                             pattern.flags)

    text = _read_text(args.inputs)
    result, counts = enforce(text, pattern, lookup)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
    else:
        sys.stdout.write(result)

    if args.report:
        total = sum(counts.values())
        for k in sorted(counts, key=lambda x: -counts[x]):
            print("%s: %d" % (k, counts[k]), file=sys.stderr)
        print("共替换 %d 处" % total, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
