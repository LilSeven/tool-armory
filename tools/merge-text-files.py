#!/usr/bin/env python3
"""文本文件合并 (merge-text-files)

按排序或显式顺序合并多个文本文件，可选插入文件名标题行与分隔线。

用法:
  python merge-text-files.py a.txt b.txt c.txt -o merged.txt
  python merge-text-files.py *.txt -o merged.txt --sorted          # 按文件名排序
  python merge-text-files.py 3.txt 1.txt -o merged.txt             # 按给定顺序（默认）
  python merge-text-files.py dir/ -o merged.txt --titles --separator "===="

说明:
  - 输入可以是文件列表或目录（目录取其中文本文件，按名排序）；
  - 默认按命令行给出的顺序合并；--sorted 改为按文件名排序；
  - --titles 在每段前插入 "===== 文件名 =====" 标题行；
  - --separator "STR" 在每段之间插入分隔线；值以 - 开头时必须写成
    --separator=STR 等号形式，否则 argparse 会把值当作选项；
  - 缺省 -o 时把结果写到标准输出。

示例命令:
  python merge-text-files.py part1.txt part2.txt -o all.txt --titles --separator=--------
"""

import argparse
import os
import sys

TEXT_EXTS = {".txt", ".md", ".log", ".csv", ".ini", ".cfg", ".json",
             ".py", ".text"}


def collect_inputs(inputs, recursive=False):
    files = []
    for p in inputs:
        if os.path.isdir(p):
            if recursive:
                for root, _dirs, names in os.walk(p):
                    for n in sorted(names):
                        ext = os.path.splitext(n)[1].lower()
                        if not TEXT_EXTS or ext in TEXT_EXTS:
                            files.append(os.path.join(root, n))
            else:
                for n in sorted(os.listdir(p)):
                    fp = os.path.join(p, n)
                    if os.path.isfile(fp):
                        ext = os.path.splitext(n)[1].lower()
                        if not TEXT_EXTS or ext in TEXT_EXTS:
                            files.append(fp)
        elif os.path.isfile(p):
            files.append(p)
        else:
            raise FileNotFoundError(p)
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="按排序或显式顺序合并多个文本文件，可选标题行与分隔线")
    ap.add_argument("inputs", nargs="+", help="输入文件或目录")
    ap.add_argument("-o", "--output", default=None,
                    help="输出文件；缺省打印到标准输出")
    ap.add_argument("--sorted", dest="sorted_", action="store_true",
                    help="按文件名排序合并（默认按命令行给定顺序）")
    ap.add_argument("--titles", action="store_true",
                    help="每段前插入 '===== 文件名 =====' 标题行")
    ap.add_argument("--separator", default=None,
                    help="每段之间插入的分隔线内容（默认无）")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="目录输入时递归收集")
    args = ap.parse_args(argv)

    try:
        files = collect_inputs(args.inputs, args.recursive)
    except FileNotFoundError as e:
        print("错误: 输入不存在: %s" % e, file=sys.stderr)
        return 2

    if len(files) < 1:
        print("错误: 未找到任何可合并的文件", file=sys.stderr)
        return 2
    if len(files) < 2 and not args.output:
        print("错误: 至少需要 2 个文件（或指定 -o）", file=sys.stderr)
        return 2

    if args.sorted_:
        files.sort(key=lambda p: (os.path.basename(p).lower(), p))

    out = sys.stdout if args.output is None else \
        open(args.output, "w", encoding="utf-8", newline="")

    try:
        for idx, fp in enumerate(files):
            if idx > 0 and args.separator:
                out.write(args.separator.rstrip("\n") + "\n")
            if args.titles:
                out.write("===== %s =====\n" % os.path.basename(fp))
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                if content and not content.endswith("\n"):
                    content += "\n"
                out.write(content)
        if args.output is None:
            out.flush()
    finally:
        if args.output is not None:
            out.close()

    if args.output is not None:
        print("已合并 %d 个文件到 %s" % (len(files), args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
