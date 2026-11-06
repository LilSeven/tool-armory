#!/usr/bin/env python3
"""按行拼接：把两个（或多个）文件的第 N 行用分隔符拼成输出的一行。

长度不齐时按需填充（--pad empty 用空串补齐，--pad fill 用指定串补齐，
--pad none 则到短文件末尾即停止）。

用法:
    python paste-lines.py a.txt b.txt
    python paste-lines.py a.txt b.txt -d " | " --pad fill --fill "N/A" -o out.txt
    python paste-lines.py a.txt b.txt -d ","            # 类似 paste -d,
"""
import argparse
import sys
from pathlib import Path


def read_lines(path: str, encoding: str):
    if path == "-":
        return [ln.rstrip("\r\n") for ln in sys.stdin]
    p = Path(path)
    if not p.is_file():
        ap = argparse.ArgumentParser()
        ap.error(f"不是文件: {path}")
    with open(p, "r", encoding=encoding, errors="replace") as fh:
        return [ln.rstrip("\r\n") for ln in fh]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="逐行用分隔符拼接两个文件的行，长度不齐时按需填充。")
    ap.add_argument("file1", help="第一个文件（'-' 表示 stdin）")
    ap.add_argument("file2", help="第二个文件（'-' 表示 stdin）")
    ap.add_argument("-d", "--delimiter", default="\t", help="行间分隔符（默认 TAB）")
    ap.add_argument("--pad", choices=["empty", "fill", "none"], default="empty",
                    help="长度不齐时：empty=空串补齐（默认）；fill=用 --fill 补齐；none=停止在短文件末尾")
    ap.add_argument("--fill", default="N/A", help="--pad fill 时的填充文本（默认 N/A）")
    ap.add_argument("-o", "--output", default="-", help="输出文件，缺省 stdout")
    ap.add_argument("--encoding", default="utf-8", help="输入编码（默认 utf-8）")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding=args.encoding, errors="replace")
    except Exception:
        pass

    lines1 = read_lines(args.file1, args.encoding)
    lines2 = read_lines(args.file2, args.encoding)

    if args.pad == "none":
        n = min(len(lines1), len(lines2))
        pad1, pad2 = [], []
    else:
        n = max(len(lines1), len(lines2))
        fill = args.fill if args.pad == "fill" else ""
        pad1 = [fill] * max(0, n - len(lines1))
        pad2 = [fill] * max(0, n - len(lines2))

    out = sys.stdout if args.output == "-" else open(
        args.output, "w", encoding="utf-8", newline="")
    try:
        seq1 = lines1 + pad1
        seq2 = lines2 + pad2
        for a, b in zip(seq1, seq2):
            out.write(a + args.delimiter + b + "\n")
    finally:
        if out is not sys.stdout:
            out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
