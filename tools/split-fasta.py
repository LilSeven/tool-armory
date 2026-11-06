#!/usr/bin/env python3
"""FASTA 序列拆分 / 抽取工具。

按 ">" 记录头把 FASTA 序列文件拆成单记录文件（每条序列一个 .fasta），
或按 ID 列表抽取子集写入单个输出文件。

用法:
    python split-fasta.py IN.fasta --outdir parts/            # 拆分
    python split-fasta.py IN.fasta --ids ids.txt -o sub.fasta # 抽取子集
    python split-fasta.py IN.fasta --ids id1,id2 -o sub.fasta

示例:
    python split-fasta.py genome.fasta --outdir records/ --prefix seq
    python split-fasta.py genome.fasta --ids "sp|P123|NAME,seqB" -o keep.fasta
    python split-fasta.py genome.fasta --ids ids.txt --invert -o rest.fasta

说明:
    - 记录 ID 取 ">" 后第一个空白前的字段；--full-header 时用整个头部
      匹配（子串匹配）。
    - --ids 三种写法等价：@file（每行一个 ID）、直接给一个已存在的文件
      路径（每行一个 ID）、逗号分隔的 ID 列表。文件中每行取第一个空白前
      的字段，因此直接粘贴 ">seq3 some desc" 这样的头部行也能匹配；
      实际按哪种方式解析会打印在输出里。
    - --invert 反选：输出不在 ID 列表中的记录。
    - 拆分时文件名取 ID 中的文件系统安全字符；抽选时保留完整记录
      （含头部描述与序列行）。
只使用 Python 标准库。
"""

import argparse
import os
import re
import sys

_ILLEGAL_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f\s]+')


def iter_records(path):
    """流式产出 (header_line_without_#, [seq_lines...])。"""
    header, seq_lines = None, []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n").rstrip("\r")
            if line.startswith(">"):
                if header is not None:
                    yield header, seq_lines
                header, seq_lines = line[1:], []
            elif header is not None:
                seq_lines.append(line)
            # 头部之前的空行/内容忽略
    if header is not None:
        yield header, seq_lines


def record_id(header):
    return header.split()[0] if header.split() else ""


def load_ids(spec):
    ids = []
    is_file = spec.startswith("@") or ("," not in spec and os.path.isfile(spec))
    if is_file:
        path = spec[1:] if spec.startswith("@") else spec
        with open(path, "r", encoding="utf-8") as f:
            ids = [ln.split()[0] for ln in f if ln.split()]
        if not ids:
            raise SystemExit("error: ID 文件为空: %s" % path)
        print("id source: file %s (%d id(s))" % (path, len(ids)))
    else:
        ids = [s.strip() for s in spec.split(",") if s.strip()]
        if not ids:
            raise SystemExit("error: ID 列表为空")
        print("id source: comma list (%d id(s))" % len(ids))
    return ids


def do_split(path, outdir, prefix):
    os.makedirs(outdir, exist_ok=True)
    used = {}
    n = 0
    for header, seq in iter_records(path):
        rid = record_id(header) or ("record_%d" % (n + 1))
        base = _ILLEGAL_FS.sub("_", rid).strip("._") or "record"
        candidate, i = base, 0
        while candidate.lower() in used:
            i += 1
            candidate = "%s_%d" % (base, i)
        used[candidate.lower()] = True
        out = os.path.join(outdir, "%s%s.fasta" % (prefix, candidate))
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(">%s\n" % header)
            for ln in seq:
                f.write(ln + "\n")
        n += 1
        print("wrote %-40s id=%s" % (os.path.basename(out), rid))
    print("total: %d record(s) -> %s" % (n, outdir))
    return 0


def do_extract(path, ids, out, full_header, invert):
    idset = set(ids)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    kept = missing = 0
    with open(out, "w", encoding="utf-8", newline="\n") as fo:
        for header, seq in iter_records(path):
            if full_header:
                hit = any(i in header for i in ids)
            else:
                hit = record_id(header) in idset
            if hit != invert:
                fo.write(">%s\n" % header)
                for ln in seq:
                    fo.write(ln + "\n")
                kept += 1
            else:
                missing += 1
    print("kept %d record(s), skipped %d -> %s" % (kept, missing, out))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="FASTA 拆分与按 ID 抽取")
    ap.add_argument("input", help="输入 FASTA 文件")
    ap.add_argument("--outdir", default=None, help="拆分输出目录（拆分模式）")
    ap.add_argument("--prefix", default="", help="拆分文件名前缀")
    ap.add_argument("--ids", default=None,
                    help='ID 列表：逗号分隔，或 @file（每行一个）（抽取模式）')
    ap.add_argument("-o", "--out", default=None, help="抽取模式的输出文件")
    ap.add_argument("--full-header", action="store_true",
                    help="用整个头部子串匹配而非仅 ID 字段")
    ap.add_argument("--invert", action="store_true", help="反选（排除列表中的记录）")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.input):
        print("error: 输入文件不存在: %s" % args.input, file=sys.stderr)
        return 2

    if args.ids is not None:
        if not args.out:
            print("error: 抽取模式需要 -o/--out 指定输出文件", file=sys.stderr)
            return 2
        return do_extract(args.input, load_ids(args.ids), args.out,
                          args.full_header, args.invert)
    if args.outdir:
        return do_split(args.input, args.outdir, args.prefix)
    print("error: 请指定 --outdir（拆分）或 --ids + --out（抽取）", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
