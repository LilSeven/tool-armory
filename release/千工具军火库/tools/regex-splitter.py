#!/usr/bin/env python3
"""正则边界切分器 — 按正则匹配位置把大文件切成若干小文件。

典型用途：按章节标题切分一本电子书、按日期行切分日志。
每个切分点（含匹配行）开始一个新文件；第一段（首个匹配之前的内容）
写入 000-preamble 或并入第一片（--keep-preamble）。

用法：
  python -I regex-splitter.py book.txt '^第.+章' --outdir parts/
  python -I regex-splitter.py log.txt '^\\d{4}-\\d{2}-\\d{2}' -o out/ -i utf-8 --dry-run
  python -I regex-splitter.py data.txt '^## ' -o out/ --prefix chap

退出码：0 成功（含 0 个切分点）；1 参数/IO 错误；2 正则编译失败。
"""
import argparse
import os
import re
import sys


def find_split_positions(text: str, rx: re.Pattern):
    """返回每个匹配在其所在行首的位置列表。"""
    positions = []
    for m in rx.finditer(text):
        # 回退到该匹配所在行的行首
        line_start = text.rfind("\n", 0, m.start()) + 1
        if positions and line_start == positions[-1]:
            continue  # 同一行多个匹配只切一次
        positions.append(line_start)
    return positions


def main(argv=None):
    ap = argparse.ArgumentParser(description="按正则匹配位置切分大文件")
    ap.add_argument("file", help="输入文件")
    ap.add_argument("pattern", help="切分边界正则（匹配行将成为新片段的首行）")
    ap.add_argument("-o", "--outdir", default="split_out", help="输出目录（默认 split_out）")
    ap.add_argument("--prefix", default="part", help="输出文件名前缀（默认 part）")
    ap.add_argument("-i", "--encoding", default="utf-8", help="输入编码（默认 utf-8）")
    ap.add_argument("-e", "--out-encoding", default=None, help="输出编码（默认同输入）")
    ap.add_argument("--keep-preamble", action="store_true",
                    help="把首个匹配之前的内容并入第一片，而不是单独存 000 文件")
    ap.add_argument("--dry-run", action="store_true", help="只打印切分计划，不写文件")
    ap.add_argument("--flags", default="", help="附加 re 标志字符：i m s x")
    args = ap.parse_args(argv)

    flags = re.MULTILINE  # 按行边界切分，默认启用多行模式
    for c in args.flags:
        flags |= {"i": re.I, "s": re.S, "x": re.X}.get(c.lower(), 0)
    try:
        rx = re.compile(args.pattern, flags)
    except re.error as exc:
        print(f"错误：正则编译失败: {exc}", file=sys.stderr)
        return 2

    try:
        with open(args.file, "r", encoding=args.encoding) as f:
            text = f.read()
    except OSError as exc:
        print(f"错误：读取失败: {exc}", file=sys.stderr)
        return 1

    positions = find_split_positions(text, rx)
    if not positions:
        print(f"未找到匹配 '{args.pattern}'，不切分。")
        return 0

    bounds = [0] if not args.keep_preamble else []
    bounds += positions
    if args.keep_preamble and positions[0] > 0:
        bounds.insert(0, 0)

    pieces = []
    for idx, start in enumerate(bounds):
        end = bounds[idx + 1] if idx + 1 < len(bounds) else len(text)
        pieces.append((start, end))
    # keep-preamble 时第一片从 0 开始，与 bounds 一致；否则首片是 preamble
    if not args.keep_preamble and bounds[0] != 0:
        pass  # bounds 已含 0 前导，仅当首匹配在文件头时去重
    if bounds and bounds[0] == 0 and not args.keep_preamble and positions[0] == 0:
        pieces = pieces[1:]  # 避免产生空 preamble

    print(f"切分点 {len(positions)} 个 -> 片段 {len(pieces)} 个")

    if args.dry_run:
        for idx, (s, e) in enumerate(pieces):
            head = text[s:e].lstrip().splitlines()[:1]
            title = head[0][:60] if head else "(空)"
            print(f"  {args.prefix}-{idx:03d}: 字符区间 {s}~{e}  首行: {title}")
        return 0

    os.makedirs(args.outdir, exist_ok=True)
    out_enc = args.out_encoding or args.encoding
    base, ext = os.path.splitext(os.path.basename(args.file))
    for idx, (s, e) in enumerate(pieces):
        name = f"{args.prefix}-{idx:03d}{ext or '.txt'}"
        path = os.path.join(args.outdir, name)
        with open(path, "w", encoding=out_enc) as f:
            f.write(text[s:e])
        print(f"  写出 {path} ({e - s} 字符)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
