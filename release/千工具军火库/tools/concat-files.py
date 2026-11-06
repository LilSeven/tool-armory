#!/usr/bin/env python3
"""多文件合并：按命令行顺序把多个文本文件拼接成一个。

用法:
    python concat-files.py a.txt b.txt c.txt -o merged.txt
    python concat-files.py a.txt b.txt -t -s=----          # 插入文件名标题行与分隔线
    cat a.txt | python concat-files.py - -t                # "-" 表示 stdin

选项:
    -o/--output    输出文件（缺省写到标准输出）
    -t/--titles    每个文件前插入标题行 "=== <文件名> ==="
    -s/--separator 文件之间插入的分隔线文本（可含重复填充，如 "----"）
    --encoding     输入编码，默认 utf-8
"""
import argparse
import sys
from pathlib import Path


def open_output(path: str):
    if path == "-":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        return sys.stdout
    return open(path, "w", encoding="utf-8", newline="")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="按顺序合并多个文本文件，可插入文件名标题行与分隔线。")
    ap.add_argument("files", nargs="+", metavar="FILE",
                    help="输入文件，按给定顺序合并；'-' 表示标准输入")
    ap.add_argument("-o", "--output", default="-", help="输出文件，缺省为 stdout")
    ap.add_argument("-t", "--titles", action="store_true",
                    help="每个文件前插入标题行 '=== 文件名 ==='")
    ap.add_argument("-s", "--separator", default="",
                    help="文件之间插入的分隔线（非空才插入；由重复首字符组成的短串会自动加长对齐）")
    ap.add_argument("--encoding", default="utf-8", help="输入编码（默认 utf-8）")
    args = ap.parse_args()

    try:
        sys.stdin.reconfigure(encoding=args.encoding, errors="replace")
    except Exception:
        pass

    sources = []
    for f in args.files:
        if f == "-":
            sources.append(("<stdin>", sys.stdin, True))
        else:
            p = Path(f)
            if not p.is_file():
                print(f"concat-files: 跳过，不是文件: {f}", file=sys.stderr)
                continue
            sources.append((f, open(p, "r", encoding=args.encoding, errors="replace"), False))

    out = open_output(args.output)
    try:
        for i, (name, fh, close_in) in enumerate(sources):
            if i > 0 and args.separator:
                out.write(args.separator + "\n")
            if args.titles:
                out.write(f"=== {name} ===\n")
            for line in fh:
                out.write(line.rstrip("\r\n") + "\n")
            if close_in and fh is not sys.stdin:
                fh.close()
    finally:
        if out is not sys.stdout:
            out.close()
        for name, fh, close_in in sources:
            if close_in and fh is not sys.stdin:
                fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
