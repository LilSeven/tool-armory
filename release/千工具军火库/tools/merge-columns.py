#!/usr/bin/env python3
"""逐行列拼接（列合并）工具。

把两个或多个文本文件按行并排拼接成一个多列文件；行数不足的文件按
指定填充串补齐。分隔符可自定义。

用法:
    python merge-columns.py A.txt B.txt [C.txt ...] [-o OUT] [-d SEP]
                           [--fill STR] [--pad-to N]

示例:
    python merge-columns.py names.txt scores.txt -o joined.txt
    python merge-columns.py a.txt b.txt -d ", " --fill "-" --pad-to 10
    python merge-columns.py a.txt b.txt | head

说明:
    - 行尾的换行符被剥离后拼接，各列之间插入 -d 指定的分隔符（默认 TAB）。
    - --fill 指定行数不足时填充的字符串（默认空串）；--pad-to 可强制
      补齐到 N 行（默认为最长输入的行数）。
    - 输出默认写到标准输出，用 -o 写入文件。
只使用 Python 标准库。
"""

import argparse
import os
import sys


def read_lines(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n").rstrip("\r") for ln in f]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="把多个文本文件逐行并排拼接（列合并）")
    ap.add_argument("files", nargs="+",
                    help="两个或多个输入文本文件")
    ap.add_argument("-o", "--out", default=None,
                    help="输出文件（默认标准输出）")
    ap.add_argument("-d", "--sep", default="\t",
                    help=r'列分隔符，默认 TAB；支持 "\t" "\n" 等转义')
    ap.add_argument("--fill", default="",
                    help='行数不足时使用的填充串，默认空串')
    ap.add_argument("--pad-to", type=int, default=None,
                    help="强制输出至少 N 行（默认为最长输入的行数）")
    args = ap.parse_args(argv)

    if len(args.files) < 2:
        print("error: 至少需要两个输入文件", file=sys.stderr)
        return 2
    for p in args.files:
        if not os.path.isfile(p):
            print("error: 输入文件不存在: %s" % p, file=sys.stderr)
            return 2

    # \t 等转义：通过 split('\n')[0] 技巧让 codecs 处理转义序列
    sep = args.sep.encode("latin-1", "backslashreplace").decode(
        "unicode_escape").encode("latin-1").decode("latin-1")
    fill = args.fill.encode("latin-1", "backslashreplace").decode(
        "unicode_escape").encode("latin-1").decode("latin-1")

    columns = [read_lines(p) for p in args.files]
    n_rows = max([len(c) for c in columns] + [args.pad_to or 0])
    if args.pad_to and args.pad_to > max(len(c) for c in columns) and not fill and fill == "":
        pass  # 允许空填充，行尾会以分隔符结尾

    out_f = open(args.out, "w", encoding="utf-8", newline="\n") if args.out else sys.stdout
    try:
        for i in range(n_rows):
            cells = [col[i] if i < len(col) else fill for col in columns]
            out_f.write(sep.join(cells) + "\n")
    finally:
        if out_f is not sys.stdout:
            out_f.close()
            print("wrote %d line(s) -> %s" % (n_rows, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
