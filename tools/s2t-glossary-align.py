#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""简繁词对照表维护：从两份平行文本（简体版 + 繁体版）自动对齐，生成简繁词对照表并导出 CSV。

对齐方式：先按行配对（行数相同直接配对，否则用 difflib 近似对齐），
再在每对行内用 difflib 找出"替换"差异段，作为候选词对，按出现次数汇总。
CSV 三列：简,繁,次数（默认无表头，可直接被 s2t-stream.py -g / term-enforce.py 作词库）。

示例命令：
  python -I s2t-glossary-align.py simp.txt trad.txt -o glossary.csv
  python -I s2t-glossary-align.py simp.txt trad.txt --min-count 2 --max-len 10
  python -I s2t-glossary-align.py simp.txt trad.txt | head
之后可用词库做转换：
  cat text.txt | python -I s2t-stream.py -d t -g glossary.csv
"""
import argparse
import csv
import difflib
import sys


def align_lines(simp_lines, trad_lines, min_ratio=0.3):
    """把两份文本的行配成对；行数不同时用 difflib 近似对齐。"""
    if len(simp_lines) == len(trad_lines):
        return list(zip(simp_lines, trad_lines))
    sm = difflib.SequenceMatcher(None, simp_lines, trad_lines, autojunk=False)
    pairs = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("equal", "replace"):
            n = min(i2 - i1, j2 - j1)
            for k in range(n):
                a, b = simp_lines[i1 + k], trad_lines[j1 + k]
                ratio = difflib.SequenceMatcher(None, a, b).ratio()
                if tag == "equal" or ratio >= min_ratio:
                    pairs.append((a, b))
    return pairs


def extract_pairs(simp_line, trad_line):
    """在一对平行行内提取替换差异段（简片段 -> 繁片段）。"""
    sm = difflib.SequenceMatcher(None, simp_line, trad_line, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "replace":
            continue
        s, t = simp_line[i1:i2], trad_line[j1:j2]
        if not s or not t or s == t:
            continue
        if s.isspace() or t.isspace():
            continue
        out.append((s, t))
    return out


def build_glossary(pairs, max_len=8, min_count=1):
    counts = {}
    for s, t in pairs:
        if len(s) > max_len or len(t) > max_len:
            continue
        counts[(s, t)] = counts.get((s, t), 0) + 1
    rows = [(s, t, c) for (s, t), c in counts.items() if c >= min_count]
    rows.sort(key=lambda r: (-r[2], r[0], r[1]))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="从平行文本生成简繁词对照表 CSV")
    ap.add_argument("simp_file", help="简体平行文本")
    ap.add_argument("trad_file", help="繁体平行文本（与简体逐行对应）")
    ap.add_argument("-o", "--output", help="输出 CSV（缺省写 stdout）")
    ap.add_argument("--min-count", type=int, default=1,
                    help="词对最少出现次数（默认 1；大语料建议 2+）")
    ap.add_argument("--max-len", type=int, default=8,
                    help="词对两侧最大长度（默认 8，滤掉整句差异）")
    ap.add_argument("--header", action="store_true",
                    help="在 CSV 首行写入表头 简,繁,次数")
    args = ap.parse_args(argv)

    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace", newline="")

    def read_lines(path):
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            return f.read().splitlines()

    simp_lines = read_lines(args.simp_file)
    trad_lines = read_lines(args.trad_file)
    if not simp_lines or not trad_lines:
        print("错误：输入文件为空", file=sys.stderr)
        return 2

    line_pairs = align_lines(simp_lines, trad_lines)
    frag_pairs = []
    for s_line, t_line in line_pairs:
        frag_pairs.extend(extract_pairs(s_line, t_line))
    rows = build_glossary(frag_pairs, max_len=args.max_len,
                          min_count=args.min_count)

    close = args.output is None
    fout = sys.stdout if close else \
        open(args.output, "w", encoding="utf-8-sig", newline="")
    try:
        w = csv.writer(fout)
        if args.header:
            w.writerow(["简", "繁", "次数"])
        for s, t, c in rows:
            w.writerow([s, t, c])
    finally:
        if not close:
            fout.close()

    used = len(line_pairs)
    print("对齐 %d/%d 行，提取 %d 个词对（写入 %s）"
          % (used, max(len(simp_lines), len(trad_lines)), len(rows),
             args.output or "stdout"), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
