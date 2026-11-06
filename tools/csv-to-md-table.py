# -*- coding: utf-8 -*-
"""CSV 转 Markdown 表格。

把 CSV 生成列宽对齐的 Markdown 表格（中文按 2 列宽计算），含表头分隔行。

用法:
    python csv-to-md-table.py in.csv                # 输出到 stdout
    python csv-to-md-table.py in.csv -o table.md    # 输出到文件
    python csv-to-md-table.py in.csv --align right  # 数据列右对齐（默认 left）

示例:
    输入 a.csv:  name,age
                 Alice,30
                 张三,7
    输出:
                 | name  | age |
                 |-------|-----|
                 | Alice | 30  |
                 | 张三  | 7   |
"""
import argparse
import csv
import sys
import io
import unicodedata


def display_width(s):
    """终端显示宽度：全角/宽字符按 2 计。"""
    w = 0
    for ch in s:
        w += 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
    return w


def pad(s, width, align="left"):
    gap = width - display_width(s)
    if gap <= 0:
        return s
    if align == "right":
        return " " * gap + s
    if align == "center":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    return s + " " * gap


def make_table(header, rows, aligns):
    # Markdown 转义管道符
    def esc(s):
        return s.replace("|", "\\|")

    header = [esc(h) for h in header]
    rows = [[esc(c) for c in r] for r in rows]
    ncol = len(header)
    widths = [display_width(h) for h in header]
    for r in rows:
        for i in range(min(ncol, len(r))):
            widths[i] = max(widths[i], display_width(r[i]))

    lines = []
    lines.append("| " + " | ".join(pad(h, widths[i]) for i, h in enumerate(header)) + " |")
    sep = []
    for i, w in enumerate(widths):
        a = aligns[i] if i < len(aligns) else "left"
        if a == "right":
            sep.append("-" * (w - 1) + ":")
        elif a == "center":
            sep.append(":" + "-" * (w - 2) + ":" if w >= 2 else ":" + "-" * max(w - 1, 1))
        else:
            sep.append("-" * w)
    lines.append("| " + " | ".join(sep) + " |")
    for r in rows:
        cells = []
        for i in range(ncol):
            cell = r[i] if i < len(r) else ""
            cells.append(pad(cell, widths[i], aligns[i] if i < len(aligns) else "left"))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="CSV 转列宽对齐的 Markdown 表格")
    ap.add_argument("input", help="输入 CSV 文件")
    ap.add_argument("-o", "--output", help="输出 Markdown 文件（缺省打印到 stdout）")
    ap.add_argument("-d", "--delimiter", default=",", help="字段分隔符（默认逗号）")
    ap.add_argument("-e", "--encoding", default="utf-8-sig", help="输入编码（默认 utf-8-sig）")
    ap.add_argument("--align", choices=["left", "right", "center"], default="left",
                    help="数据列对齐方式（默认 left，表头恒为 left）")
    args = ap.parse_args()

    with io.open(args.input, "r", encoding=args.encoding, newline="") as f:
        rows = [r for r in csv.reader(f, delimiter=args.delimiter) if any(c != "" for c in r)]

    if not rows:
        print("错误：输入为空", file=sys.stderr)
        return 1

    header = rows[0]
    data = rows[1:]
    aligns = [args.align] * len(header)
    table = make_table(header, data, aligns)

    if args.output:
        with io.open(args.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(table + "\n")
        print("已写入 %s（%d 数据行）" % (args.output, len(data)))
    else:
        sys.stdout.buffer.write((table + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
