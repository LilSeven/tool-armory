#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""水印广告行删除——按规则文件（正则列表）删除小说 TXT 中的水印/广告行。

逐行应用规则文件中的正则（每行一条，# 开头为注释，空行忽略），命中即整行删除，
其余行原样保留、顺序不变。不提供 -r 规则文件时使用内置规则（覆盖
「本书由××整理」「更多精校小说」「请记住本书」等常见水印）。

用法:
    python watermark-remove.py input.txt -r rules.txt -o clean.txt --stats
    python watermark-remove.py input.txt                     # 内置规则，打印到 stdout
    python watermark-remove.py input.txt --in-place --stats  # 原地覆盖输入文件
    python watermark-remove.py input.txt -o clean.txt --out-encoding gbk

规则文件示例 rules.txt:
    # 每行一条 Python 正则
    ^本书由.{0,30}整理
    ^更多精校小说
    www\.[A-Za-z0-9.-]+

注意: --in-place 会按 --out-encoding（默认 utf-8）重写输入文件。
退出码: 0=成功; 2=参数/文件/正则错误。
"""

import argparse
import re
import sys
from pathlib import Path

BUILTIN_RULES = [
    r"本书由.{0,30}整理",
    r"更多精校小说",
    r"请记住本书.{0,30}",
    r"一秒?记住.{0,30}",
    r"章节?错误?点[此这]里",
    r"(?:最新|最快|全文|正版)阅读.{0,20}",
    r"\b(?:www|wap|m)\.[A-Za-z0-9-]+\.[A-Za-z]{2,8}\S*",
]


def _reconfig():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def die(msg):
    print(f"错误: {msg}", file=sys.stderr)
    sys.exit(2)


def read_text(path, encoding):
    raw = Path(path).read_bytes()
    if encoding != "auto":
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError) as exc:
            die(f"无法用 {encoding} 解码 {path}: {exc}")
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def write_text(path, text, encoding):
    with open(path, "w", encoding=encoding, newline="") as fh:
        fh.write(text)


def load_rules(path):
    rules = []
    try:
        content = read_text(path, "auto")
    except OSError as exc:
        die(f"读取规则文件失败: {exc}")
    for lineno, raw in enumerate(content.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rules.append(re.compile(line))
        except re.error as exc:
            die(f"规则文件 {path} 第 {lineno} 行正则无效: {line!r} ({exc})")
    if not rules:
        die(f"规则文件 {path} 中没有有效规则")
    return rules


def main(argv=None):
    _reconfig()
    ap = argparse.ArgumentParser(
        prog="watermark-remove",
        description="按规则文件（正则列表）删除小说 TXT 中的水印/广告行",
    )
    ap.add_argument("input", help="输入 TXT 文件")
    ap.add_argument("-r", "--rules", help="规则文件（每行一条正则, # 为注释）; 缺省用内置规则")
    ap.add_argument("-o", "--output", help="输出文件; 缺省打印到 stdout")
    ap.add_argument("--in-place", action="store_true", help="直接覆盖输入文件（与 -o 互斥）")
    ap.add_argument("--stats", action="store_true", help="在 stderr 打印删除统计")
    ap.add_argument("--encoding", default="auto", help="输入编码, auto=尝试 utf-8/gb18030/big5")
    ap.add_argument("--out-encoding", default="utf-8", help="输出文件编码（默认 utf-8）")
    args = ap.parse_args(argv)

    if args.in_place and args.output:
        die("--in-place 与 -o 不能同时使用")

    rules = load_rules(args.rules) if args.rules else [re.compile(r) for r in BUILTIN_RULES]
    try:
        text = read_text(args.input, args.encoding)
    except OSError as exc:
        die(f"读取输入失败: {exc}")

    kept, removed = [], []
    for lineno, line in enumerate(text.splitlines(), 1):
        if any(rx.search(line) for rx in rules):
            removed.append((lineno, line))
        else:
            kept.append(line)

    out_text = "\n".join(kept) + ("\n" if kept else "")
    if args.in_place:
        write_text(args.input, out_text, args.out_encoding)
        dest = args.input
    elif args.output:
        write_text(args.output, out_text, args.out_encoding)
        dest = args.output
    else:
        sys.stdout.write(out_text)
        dest = "<stdout>"

    if args.stats:
        total = len(kept) + len(removed)
        pct = (100.0 * len(removed) / total) if total else 0.0
        print(f"[watermark-remove] 输入 {total} 行, 删除 {len(removed)} 行 ({pct:.1f}%), "
              f"保留 {len(kept)} 行 → {dest}", file=sys.stderr)
        for lineno, line in removed[:20]:
            print(f"  删除 L{lineno}: {line.strip()[:60]}", file=sys.stderr)
        if len(removed) > 20:
            print(f"  ... 其余 {len(removed) - 20} 行省略", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
