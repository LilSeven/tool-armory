#!/usr/bin/env python3
"""按空行分块拆分 (split-by-empty-line)

把文本按空行分块（段落或记录），每块保存为单独文件，或带序号输出到
标准输出。连续多个空行视为一个分隔符；--min-lines N 可要求块内至少
有 N 行非空内容才算一个块。

用法:
  python split-by-empty-line.py notes.txt -o outdir          # 每块一个文件
  python split-by-empty-line.py notes.txt -o outdir --pad 4  # 文件名 0001.txt
  python split-by-empty-line.py notes.txt                    # 不给 -o 则打印编号块
  python split-by-empty-line.py notes.txt -o outdir --sep "|" # 以 | 为分隔行
  python split-by-empty-line.py notes.txt -o outdir --no-blank # 去除块内空行

示例命令:
  python split-by-empty-line.py records.txt -o ./chunks --pad 3
"""

import argparse
import os
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="把文本按空行分块，每块保存为单独文件或带序号输出")
    ap.add_argument("input", help="输入文本文件（- 表示标准输入）")
    ap.add_argument("-o", "--outdir", default=None,
                    help="输出目录；缺省则把分块带序号打印到标准输出")
    ap.add_argument("--pad", type=int, default=0,
                    help="文件名序号补零位数（默认 0，即 1.txt/2.txt）")
    ap.add_argument("--ext", default=".txt", help="输出扩展名（默认 .txt）")
    ap.add_argument("--sep", default=None,
                    help="用该行内容（如 ---）作为分块分隔行，替代空行")
    ap.add_argument("--min-lines", type=int, default=1,
                    help="块内至少多少行非空内容才算块（默认 1）")
    ap.add_argument("--no-blank", action="store_true",
                    help="输出块时去除块内部的空行")
    args = ap.parse_args(argv)

    if args.min_lines < 1:
        print("错误: --min-lines 必须 >= 1", file=sys.stderr)
        return 2

    if args.input == "-":
        text = sys.stdin.read()
    else:
        if not os.path.isfile(args.input):
            print("错误: 输入文件不存在: %s" % args.input, file=sys.stderr)
            return 2
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()

    lines = text.splitlines()
    blocks = []
    cur = []

    def flush():
        nonlocal cur
        body = [l for l in cur if l.strip()]
        if len(body) >= args.min_lines:
            blocks.append(list(cur))
        cur = []

    for line in lines:
        if args.sep is not None:
            if line.strip() == args.sep.strip():
                flush()
                continue
        elif line.strip() == "":
            flush()
            continue
        cur.append(line)
    flush()

    if not blocks:
        print("未分出任何块。", file=sys.stderr)
        return 1

    def clean(ls):
        return [l for l in ls if l.strip()] if args.no_blank else ls

    if args.outdir is None:
        for i, b in enumerate(blocks, 1):
            print("===== 块 %d (%d 行) =====" % (i, len(clean(b))))
            print("\n".join(clean(b)))
        print("共 %d 块" % len(blocks))
        return 0

    os.makedirs(args.outdir, exist_ok=True)
    for i, b in enumerate(blocks, 1):
        if args.pad:
            fname = "%0*d%s" % (args.pad, i, args.ext)
        else:
            fname = "%d%s" % (i, args.ext)
        with open(os.path.join(args.outdir, fname), "w",
                  encoding="utf-8", newline="") as f:
            f.write("\n".join(clean(b)) + "\n")
    print("共输出 %d 个文件到 %s" % (len(blocks), args.outdir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
