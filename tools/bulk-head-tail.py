#!/usr/bin/env python3
"""批量截取预览：为多个文本文件输出前 N 行或后 N 行，汇入一个汇总文件，带来源文件名标注。

用途
    对一批文本/日志文件生成预览摘要（head 或 tail），每段前标注来源文件名，
    便于快速浏览目录下所有文本文件的开头或结尾内容。

示例命令
    python bulk-head-tail.py -o preview.txt -n 5 --mode head *.log *.txt
    python bulk-head-tail.py -o preview.txt -n 20 --mode tail logs/*.log
    python bulk-head-tail.py -o preview.txt -n 3 -e utf-8 ./*.md

参数
    patterns    一个或多个 glob 通配符（支持 ** 递归）
    -o/--output 输出汇总文件路径（默认 preview.txt）
    -n/--lines  每个文件截取的行数（默认 10，可为 0 表示全部）
    --mode      head（前 N 行，默认）或 tail（后 N 行）
    -e/--encoding 读取编码（默认 utf-8，错误替换为占位符）
    --sep       段与段之间的分隔行（默认 '=*'x60）
"""
import argparse
import glob
import io
import os
import sys

def iter_files(patterns):
    seen = set()
    for pat in patterns:
        for path in sorted(glob.glob(pat, recursive=True)):
            if os.path.isfile(path) and not os.path.islink(path):
                ap = os.path.abspath(path)
                if ap not in seen:
                    seen.add(ap)
                    yield path

def read_lines(path, encoding):
    with io.open(path, "r", encoding=encoding, errors="replace") as f:
        return f.read().splitlines()

def preview(path, n, mode, encoding):
    lines = read_lines(path, encoding)
    if n and n > 0:
        picked = lines[:n] if mode == "head" else lines[-n:]
        total = len(lines)
        head_note = "前" if mode == "head" else "后"
        note = "（全部 %d 行）" % total if total <= n else \
               "（%s %d 行 / 共 %d 行）" % (head_note, len(picked), total)
    else:
        picked = lines
        note = "（全部 %d 行）" % len(lines)
    return picked, note

def main(argv=None):
    ap = argparse.ArgumentParser(description="批量生成文本文件 head/tail 预览汇总")
    ap.add_argument("patterns", nargs="+", help="glob 通配符，如 *.log 或 logs/**/*.log")
    ap.add_argument("-o", "--output", default="preview.txt", help="输出汇总文件（默认 preview.txt）")
    ap.add_argument("-n", "--lines", type=int, default=10, help="每个文件截取行数（默认 10，0=全部）")
    ap.add_argument("--mode", choices=["head", "tail"], default="head", help="截取头部或尾部（默认 head）")
    ap.add_argument("-e", "--encoding", default="utf-8", help="读取编码（默认 utf-8）")
    ap.add_argument("--sep", default="=" * 60, help="段间分隔行")
    args = ap.parse_args(argv)

    if args.lines < 0:
        ap.error("--lines 不能为负数")

    files = list(iter_files(args.patterns))
    out_path = args.output
    count = 0
    with io.open(out_path, "w", encoding="utf-8", newline="\n") as out:
        if not files:
            out.write("未匹配到任何文件。\n")
        for path in files:
            try:
                picked, note = preview(path, args.lines, args.mode, args.encoding)
            except OSError as e:
                out.write("### %s\n[读取失败: %s]\n%s\n" % (path, e, args.sep))
                continue
            out.write("### 来源文件: %s %s\n" % (path, note))
            for line in picked:
                out.write(line + "\n")
            out.write(args.sep + "\n")
            count += 1
            print("已写入预览: %s" % path)
    print("完成：共 %d 个文件，汇总写入 %s" % (count, out_path))
    return 0

if __name__ == "__main__":
    sys.exit(main())
