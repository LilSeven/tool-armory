# -*- coding: utf-8 -*-
"""CSV 分隔符转换。

在逗号、制表符、分号、管道等分隔符之间转换，基于 csv 模块解析与写出，
正确处理带引号字段与内嵌换行。

用法:
    python csv-delim-convert.py in.csv --to tab          # 逗号 -> 制表符
    python csv-delim-convert.py in.tsv --to comma -o out.csv
    python csv-delim-convert.py in.csv --to pipe --from semi

可选分隔符: comma(,) tab(\t) semi(;) pipe(|) 以及单字符 --from/--to 自定义。

示例:
    python csv-delim-convert.py data.csv --to semi -o data_s.csv
"""
import argparse
import csv
import sys
import io

NAMED = {"comma": ",", "tab": "\t", "semi": ";", "pipe": "|"}


def resolve(name):
    if name in NAMED:
        return NAMED[name]
    if len(name) == 1:
        return name
    raise SystemExit("错误：未知分隔符 %r（可用: %s 或单个字符）" % (name, ", ".join(sorted(NAMED))))


def main():
    ap = argparse.ArgumentParser(description="CSV 分隔符转换（csv 模块处理引号与换行）")
    ap.add_argument("input", help="输入 CSV/TSV 文件")
    ap.add_argument("-o", "--output", help="输出文件（缺省打印到 stdout）")
    ap.add_argument("--from", dest="src", default="comma", help="源分隔符（默认 comma）")
    ap.add_argument("--to", dest="dst", default="tab", help="目标分隔符（默认 tab）")
    ap.add_argument("-e", "--encoding", default="utf-8-sig", help="输入编码（默认 utf-8-sig）")
    ap.add_argument("--no-header", action="store_true", help="输入没有表头（仅影响行数统计）")
    args = ap.parse_args()

    src = resolve(args.src)
    dst = resolve(args.dst)

    with io.open(args.input, "r", encoding=args.encoding, newline="") as f:
        rows = list(csv.reader(f, delimiter=src))

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=dst, lineterminator="\n")
    writer.writerows(rows)

    if args.output:
        with io.open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(buf.getvalue())
        print("已写入 %s（%d 行，%s -> %s）" % (args.output, len(rows), repr(src), repr(dst)))
    else:
        sys.stdout.buffer.write(buf.getvalue().encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
