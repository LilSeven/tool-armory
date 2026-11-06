#!/usr/bin/env python3
"""ASCII 表格渲染：把 CSV/JSON 数据渲染成带边框对齐的终端表格。

中文等多字节字符按 East Asian Width 计算显示宽度对齐。
输入按扩展名识别：.json / .jsonl / 其他按 CSV（首行为表头）。

用法:
    python ascii-table.py data.csv
    python ascii-table.py data.json
    cat data.csv | python ascii-table.py - --delim "," --align right:3

示例命令:
    python ascii-table.py users.csv --align left
    python ascii-table.py rows.jsonl
"""
import argparse
import csv
import io
import json
import sys
import unicodedata

BOX = {
    # tl, hz, top-junction, tr, bottom-junction, bl, br, vt
    "ascii": ("+", "-", "+", "+", "+", "+", "+", "|"),
    "unicode": ("┌", "─", "┬", "┐", "┴", "└", "┘", "│"),
}


def dwidth(s: str) -> int:
    """East Asian Width 计算显示宽度：W/F 算 2，其余算 1（组合字符计 0）。"""
    w = 0
    for ch in s:
        if unicodedata.combining(ch):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def pad(s: str, width: int, align: str) -> str:
    gap = width - dwidth(s)
    if gap <= 0:
        return s
    if align == "right":
        return " " * gap + s
    if align == "center":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    return s + " " * gap


def load_rows(path: str, encoding: str, delim: str, fmt: str) -> list:
    if path == "-":
        text = sys.stdin.buffer.read().decode(encoding)
        if fmt == "auto":
            try:
                json.loads(text)
                fmt = "json"
            except json.JSONDecodeError:
                first = next((ln for ln in text.splitlines() if ln.strip()), "")
                fmt = "jsonl" if first.lstrip()[:1] in ("[", "{") else "csv"
    else:
        with open(path, "r", encoding=encoding, newline="") as f:
            text = f.read()
        if fmt == "auto":
            if path.endswith(".json"):
                fmt = "json"
            elif path.endswith((".jsonl", ".ndjson")):
                fmt = "jsonl"
            else:
                fmt = "csv"
    if fmt == "json":
        obj = json.loads(text)
        if not isinstance(obj, list) or not all(isinstance(r, dict) for r in obj):
            raise SystemExit("错误: JSON 输入须为对象数组")
        headers = []
        for r in obj:
            for k in r:
                if k not in headers:
                    headers.append(k)
        return [headers] + [[str(r.get(h, "")) for h in headers] for r in obj]
    if fmt == "jsonl":
        rows = []
        headers = []
        for n, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise SystemExit(f"错误: 第 {n} 行不是 JSON 对象")
            for k in obj:
                if k not in headers:
                    headers.append(k)
            rows.append(obj)
        return [headers] + [[str(r.get(h, "")) for h in headers] for r in rows]
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    return [r for r in reader if r]


def main() -> int:
    ap = argparse.ArgumentParser(description="CSV/JSON 渲染成带边框对齐的终端表格")
    ap.add_argument("file", help="输入文件（.json/.jsonl/CSV）；'-' 表示 stdin")
    ap.add_argument("-d", "--delim", default=",", help="CSV 分隔符（默认逗号）")
    ap.add_argument("-e", "--encoding", default="utf-8", help="文件编码（默认 utf-8）")
    ap.add_argument("-s", "--style", choices=["ascii", "unicode"], default="ascii",
                    help="边框风格（默认 ascii，即 +--+ 式）")
    ap.add_argument("--align", default="left",
                    help="对齐方式：left/right/center 全局，或 'left,right:2' 按列")
    ap.add_argument("-f", "--format", choices=["auto", "csv", "json", "jsonl"],
                    default="auto", help="输入格式（默认按扩展名/stdin 内容自动识别）")
    args = ap.parse_args()

    rows = load_rows(args.file, args.encoding, args.delim, args.format)
    if not rows:
        print("(空输入)", file=sys.stderr)
        return 0
    ncols = len(rows[0])
    rows = [r + [""] * (ncols - len(r)) if len(r) < ncols else r[:ncols] for r in rows]

    aligns = ["left"] * ncols
    for i, part in enumerate(args.align.split(",")):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            a, idx = part.split(":")
            idx = int(idx)
        else:
            a, idx = part, i
        if 0 <= idx < ncols:
            aligns[idx] = a

    widths = [max(dwidth(r[c]) for r in rows) for c in range(ncols)]
    tl, hz, tj, tr, bj, bl, br, vt = BOX[args.style]
    top = tl + tj.join(hz * (w + 2) for w in widths) + tr
    bottom = bl + bj.join(hz * (w + 2) for w in widths) + br
    out = [top]
    out.append(vt + vt.join(
        f" {pad(rows[0][c], widths[c], aligns[c])} " for c in range(ncols)) + vt)
    out.append(top)
    for row in rows[1:]:
        out.append(vt + vt.join(
            f" {pad(row[c], widths[c], aligns[c])} " for c in range(ncols)) + vt)
    out.append(bottom)
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
