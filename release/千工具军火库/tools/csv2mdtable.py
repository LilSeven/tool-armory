#!/usr/bin/env python3
"""CSV 转 Markdown 表格 — 把 CSV 转成按列宽对齐的 Markdown 表格并自动转义竖线。

读取 CSV（可用 --delimiter / --encoding 调整），计算每列最大显示宽度，
输出对齐的 Markdown 表格；单元格中的竖线 | 转义为 \\|，换行转为 <br>。

用法:
    python csv2mdtable.py input.csv                 # 输出到 stdout
    python csv2mdtable.py input.csv -o out.md       # 输出到文件
    python csv2mdtable.py input.csv --align right   # 右对齐
    echo 'a,b' | python csv2mdtable.py -            # 从 stdin 读取

示例:
    $ printf 'name,note\nli,"a|b"\n' | python csv2mdtable.py -
    | name | note  |
    | ---- | ----- |
    | li   | a\\|b |
"""

import argparse
import csv
import io
import sys


def escape_cell(text):
    """转义 Markdown 表格特殊字符：竖线与换行。"""
    return text.replace("|", r"\|").replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")


def display_width(s):
    """简单显示宽度：CJK 等宽字符按 2 计。"""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def pad(s, width, align):
    gap = width - display_width(s)
    if gap <= 0:
        return s
    if align == "right":
        return " " * gap + s
    if align == "center":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    return s + " " * gap


def csv_to_md(rows, align="left"):
    """rows: 可迭代的字符串列表列表，第一行为表头。返回 Markdown 表格文本。"""
    rows = [row for row in rows if row]  # 跳过空行
    if not rows:
        raise ValueError("CSV 内容为空")
    ncols = max(len(r) for r in rows)
    rows = [r + [""] * (ncols - len(r)) for r in rows]
    escaped = [[escape_cell(c) for c in r] for r in rows]
    widths = [max(display_width(r[i]) for r in escaped) for i in range(ncols)]
    widths = [max(w, 3) for w in widths]  # 分隔行至少 ---

    header = escaped[0]
    sep = ["-" * w for w in widths]
    out = ["| " + " | ".join(pad(c, w, align) for c, w in zip(header, widths)) + " |",
           "| " + " | ".join(sep) + " |"]
    for r in escaped[1:]:
        out.append("| " + " | ".join(pad(c, w, align) for c, w in zip(r, widths)) + " |")
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description="把 CSV 转成按列宽对齐的 Markdown 表格并自动转义竖线")
    parser.add_argument("input", nargs="?", default="-", help="输入 CSV 文件路径，'-' 表示 stdin")
    parser.add_argument("-o", "--output", help="输出文件路径（缺省打印到 stdout）")
    parser.add_argument("-d", "--delimiter", default=",", help="字段分隔符（默认 ,）")
    parser.add_argument("-e", "--encoding", default="utf-8-sig", help="输入编码（默认 utf-8-sig）")
    parser.add_argument("--align", choices=["left", "right", "center"], default="left",
                        help="单元格对齐方式（默认 left）")
    parser.add_argument("--no-header", action="store_true", help="输入没有表头行，第一行也按数据输出")
    args = parser.parse_args(argv)

    try:
        if args.input == "-":
            raw = sys.stdin.read()
        else:
            with open(args.input, "r", encoding=args.encoding, newline="") as fh:
                raw = fh.read()
    except OSError as exc:
        print(f"错误: 读取文件失败: {exc}", file=sys.stderr)
        return 1

    rows = list(csv.reader(io.StringIO(raw), delimiter=args.delimiter))
    if args.no_header and rows:
        rows.insert(0, ["col%d" % i for i in range(max(len(r) for r in rows))])

    try:
        result = csv_to_md(rows, align=args.align)
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(result + "\n")
        print(f"已写入 {args.output}")
    else:
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
