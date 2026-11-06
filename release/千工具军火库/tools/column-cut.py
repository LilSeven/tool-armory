#!/usr/bin/env python3
"""增强版列提取：按列号（多范围、可重排/重复）、分隔符或正则捕获组提取文本列。

用法:
    python column-cut.py -f 1,3,5-7 data.txt               # 按列号（默认按空白切分）
    python column-cut.py -d "," -f 3,1 data.csv            # 按逗号切分并重排（3 在前 1 在后）
    python column-cut.py -f 1-3 --reorder --missing "-" f.txt  # 允许重复列，缺失填 "-"
    python column-cut.py -r "(\\w+)@(\\w+)" -G 2,1 mails.txt   # 按正则组提取并交换
    python column-cut.py -f 2 < data.txt                   # 读 stdin

选项:
    -f/--fields    列号/范围，如 "1,3,5-7"（1 起；0 表示整行）
    -d/--delim     输入分隔符（缺省按连续空白切分）
    -r/--regex     每行应用此正则，提取捕获组
    -G/--groups    正则模式下输出的组号序列，如 "2,1"；缺省输出全部组；group(0) 为整匹配
    --reorder      按书写顺序输出列（默认也是书写顺序；允许重复与乱序则建议显式加此开关）
    -D/--out-delim 输出分隔符（默认 TAB）
    --missing      列不存在时的填充文本（默认空串）
    -c/--comment   跳过以该前缀开头的注释行（如 "#")
"""
import argparse
import re
import sys
from pathlib import Path


def parse_fields(spec: str):
    """把 '1,3,5-7' 解析为按书写顺序（含重复）的列号列表。"""
    cols = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            try:
                lo_i, hi_i = int(lo), int(hi)
            except ValueError:
                raise SystemExit(f"column-cut: 非法范围: {part}")
            if lo_i > hi_i:
                lo_i, hi_i = hi_i, lo_i
            cols.extend(range(lo_i, hi_i + 1))
        else:
            try:
                cols.append(int(part))
            except ValueError:
                raise SystemExit(f"column-cut: 非法列号: {part}")
    if not cols:
        raise SystemExit("column-cut: --fields 为空")
    return cols


def main() -> int:
    ap = argparse.ArgumentParser(
        description="按列号、分隔符或正则组提取文本列，支持重排列与多范围。")
    ap.add_argument("file", nargs="?", default="-", help="输入文件（缺省或 '-' 为 stdin）")
    ap.add_argument("-f", "--fields", default="1", help="列号/范围，如 1,3,5-7（默认 1）")
    ap.add_argument("-d", "--delim", default=None,
                    help="输入分隔符；缺省按连续空白切分")
    ap.add_argument("-r", "--regex", default=None, help="按正则捕获组提取（与 -f 二选一）")
    ap.add_argument("-G", "--groups", default=None, help="正则模式输出组号序列，如 2,1")
    ap.add_argument("--reorder", action="store_true",
                    help="显式启用按书写顺序重排输出（允许乱序与重复）")
    ap.add_argument("-D", "--out-delim", default="\t", help="输出分隔符（默认 TAB）")
    ap.add_argument("--missing", default="", help="列不存在时的填充文本（默认空）")
    ap.add_argument("-c", "--comment", default=None, help="跳过以该前缀开头的行")
    ap.add_argument("--encoding", default="utf-8", help="输入编码（默认 utf-8）")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding=args.encoding, errors="replace")
    except Exception:
        pass

    if args.regex:
        rx = re.compile(args.regex)
        groups = ([int(g) for g in args.groups.split(",") if g.strip()]
                  if args.groups else None)
        cols = None
    else:
        cols = parse_fields(args.fields)
        if not args.reorder:
            # 保留书写顺序（去重由调用语义决定；这里保持原样即允许重复）
            pass

    if args.file != "-":
        p = Path(args.file)
        if not p.is_file():
            ap.error(f"不是文件: {args.file}")
        fh = open(p, "r", encoding=args.encoding, errors="replace")
    else:
        fh = sys.stdin

    out = sys.stdout
    try:
        for line in fh:
            line = line.rstrip("\r\n")
            if args.comment and line.startswith(args.comment):
                continue
            if args.regex:
                m = rx.search(line)
                if not m:
                    continue
                if groups is None:
                    parts = [g if g is not None else args.missing
                             for g in m.groups()]
                else:
                    parts = []
                    for g in groups:
                        val = m.group(0) if g == 0 else m.group(g)
                        parts.append(val if val is not None else args.missing)
            else:
                pieces = (line.split(args.delim) if args.delim is not None
                          else line.split())
                parts = []
                for c in cols:
                    if 0 in cols and c == 0:
                        parts.append(line)
                    elif 1 <= c <= len(pieces):
                        parts.append(pieces[c - 1])
                    else:
                        parts.append(args.missing)
            out.write(args.out_delim.join(parts) + "\n")
    finally:
        if fh is not sys.stdin:
            fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
