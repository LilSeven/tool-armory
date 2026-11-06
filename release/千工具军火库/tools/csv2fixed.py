#!/usr/bin/env python3
"""csv2fixed.py -- 把 CSV 各列按指定宽度左/右对齐填充，输出为定宽表格文本。

用法:
    python csv2fixed.py input.csv --widths "10,6,8" -o table.txt
    python csv2fixed.py input.csv --widths "10L,6R,8L"
    python csv2fixed.py input.csv --sep " " --auto -o table.txt

参数:
    INPUT              输入 CSV/TSV 文件路径；"-" 读 stdin
    -o, --output       输出文件，缺省 stdout
    --widths           逗号分隔的各列宽度，可带 L/R 后缀指明对齐方向，
                       如 "10L,6R,8"；无后缀默认左对齐；截断过长字段
    --sep              列间分隔串，默认两个空格
    --auto             自动按最长字段计算每列宽度（右对齐数值、左对齐其余）
    --tsv              源文件按制表符解析
    --auto-sep         自动探测源分隔符（, \\t ; | 取出现最多者），默认对 .csv/.txt
                       逗号；与 --tsv 互斥
    -e, --encoding     文件编码，默认 utf-8

示例:
    python csv2fixed.py data.csv --widths "20L,8R,10" -o report.txt
    python csv2fixed.py data.csv --auto --sep " | "
"""
import argparse
import csv
import sys


def parse_widths(spec):
    """解析 "10L,6R,8" -> [(10,'L'),(6,'R'),(8,'L')]。"""
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        align = "L"
        num = part
        if part and part[-1].upper() in ("L", "R") and len(part) > 1:
            align = part[-1].upper()
            num = part[:-1]
        try:
            w = int(num)
        except ValueError:
            raise SystemExit(f"错误: 宽度项 {part!r} 不是整数")
        if w <= 0:
            raise SystemExit(f"错误: 宽度项 {part!r} 必须为正整数")
        out.append((w, align))
    if not out:
        raise SystemExit("错误: --widths 为空")
    return out


def detect_sep(lines, tsv=False, auto_sep=False):
    if tsv:
        return "\t"
    if auto_sep:
        best, best_n = ",", -1
        for c in ",\t;|":
            n = sum(ln.count(c) for ln in lines[:50])
            if n > best_n:
                best, best_n = c, n
        if best_n <= 0:
            raise SystemExit("错误: --auto-sep 未能探测到分隔符，请用 --tsv "
                             "或源文件含逗号")
        return best
    return ","


def fmt_cell(text, width, align):
    text = text.replace("\n", " ").replace("\r", " ")
    if len(text) > width:
        text = text[:width]
    if align == "R":
        return text.rjust(width)
    return text.ljust(width)


def main():
    ap = argparse.ArgumentParser(
        description="把 CSV 各列按指定宽度对齐填充，输出定宽表格文本")
    ap.add_argument("input", help="输入 CSV 文件，或 '-' 表示 stdin")
    ap.add_argument("-o", "--output", help="输出文件，缺省 stdout")
    ap.add_argument("--widths", help='各列宽度与对齐，如 "10L,6R,8"')
    ap.add_argument("--sep", default="  ", help='列间分隔串，默认两个空格')
    ap.add_argument("--auto", action="store_true",
                    help="自动按最长字段计算宽度")
    ap.add_argument("--tsv", action="store_true", help="源按制表符解析")
    ap.add_argument("--auto-sep", action="store_true",
                    help="自动探测源分隔符（, \\t ; |）")
    ap.add_argument("-e", "--encoding", default="utf-8")
    args = ap.parse_args()

    if args.tsv and args.auto_sep:
        raise SystemExit("错误: --tsv 与 --auto-sep 互斥")

    if args.input == "-":
        text = sys.stdin.buffer.read().decode(args.encoding)
    else:
        try:
            with open(args.input, "r", encoding=args.encoding, newline="") as f:
                text = f.read()
        except OSError as exc:
            raise SystemExit(f"错误: 无法读取 {args.input}: {exc}")

    lines = [ln for ln in text.splitlines() if ln.strip()]
    sep = detect_sep(lines, args.tsv, args.auto_sep)
    rows = list(csv.reader(lines, delimiter=sep))

    if not rows:
        raise SystemExit("错误: 输入没有数据行")

    ncol = max(len(r) for r in rows)

    if args.auto:
        widths = []
        for c in range(ncol):
            cells = [r[c] for r in rows if c < len(r)]
            w = max((len(x) for x in cells), default=1)
            numeric = bool(cells) and all(
                x and (x.lstrip("+-").replace(".", "", 1).isdigit())
                for x in cells)
            widths.append((w, "R" if numeric else "L"))
    elif args.widths:
        widths = parse_widths(args.widths)
        if len(widths) < ncol:
            raise SystemExit(
                f"错误: 数据有 {ncol} 列，但 --widths 只给了 {len(widths)} 列")
    else:
        raise SystemExit("错误: 需要 --widths 或 --auto 之一")

    out_lines = []
    for row in rows:
        cells = []
        for c in range(ncol):
            val = row[c] if c < len(row) else ""
            w, align = widths[c]
            cells.append(fmt_cell(val, w, align))
        out_lines.append(args.sep.join(cells).rstrip())

    out_text = "\n".join(out_lines) + "\n"

    if args.output:
        with open(args.output, "w", encoding=args.encoding, newline="") as f:
            f.write(out_text)
        print(f"已写入 {args.output}（{len(rows)} 行 x {ncol} 列）",
              file=sys.stderr)
    else:
        sys.stdout.write(out_text)


if __name__ == "__main__":
    main()
