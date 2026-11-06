#!/usr/bin/env python3
"""HTML 表格抽取为 CSV。

用 html.parser 解析 HTML 文件中的所有 <table>，每个表格存为一个 CSV 文件
（默认输出到 <输入名>_tableN.csv，N 从 1 开始）。支持 colspan/rowspan 合并单元格。

用法:
    python html-table-to-csv.py input.html [-o 输出目录] [--encoding utf-8]

示例:
    python html-table-to-csv.py page.html -o out/
"""
import argparse
import csv
import os
import sys
from html.parser import HTMLParser


class Table:
    def __init__(self):
        self.rows = []          # 每行是 [cell, ...]，cell 为 {"text":..,"colspan":..,"rowspan":..}
        self._current = None

    def start_row(self):
        self._current = []

    def end_row(self):
        if self._current is not None:
            self.rows.append(self._current)
        self._current = None

    def add_cell(self, text, colspan, rowspan):
        raw = "".join(text) if isinstance(text, list) else text
        self._current.append({"text": " ".join(raw.split()), "colspan": colspan, "rowspan": rowspan})

    def finalize(self):
        """展开 colspan/rowspan，返回规则二维数组。"""
        if not self.rows:
            return []
        grid = {}  # (r, c) -> text
        max_c = 0
        for r, row in enumerate(self.rows):
            c = 0
            for cell in row:
                while (r, c) in grid:
                    c += 1
                for dr in range(max(cell["rowspan"], 1)):
                    for dc in range(max(cell["colspan"], 1)):
                        grid[(r + dr, c + dc)] = cell["text"] if (dr == 0 and dc == 0) else ""
                c += cell["colspan"]
            max_c = max(max_c, c)
        n_rows = len(self.rows)
        return [[grid.get((r, c), "") for c in range(max_c)] for r in range(n_rows)]


class TableExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self._stack = []        # 当前打开的 table 层级里的状态
        self._skip_depth = 0    # 位于 script/style 内则跳过文本

    @property
    def _in_table(self):
        return bool(self._stack)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self._stack.append(Table())
            return
        if not self._in_table:
            if tag in ("script", "style"):
                self._skip_depth = 1
            return
        t = self._stack[-1]
        if tag == "tr":
            t.start_row()
        elif tag in ("td", "th"):
            try:
                colspan = max(int(a.get("colspan", "1") or 1), 1)
            except ValueError:
                colspan = 1
            try:
                rowspan = max(int(a.get("rowspan", "1") or 1), 1)
            except ValueError:
                rowspan = 1
            t._pending_cell = {"text": [], "colspan": colspan, "rowspan": rowspan}
            t._cell_open = True
        elif tag in ("script", "style"):
            self._skip_depth = 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth = 0
            return
        if not self._in_table:
            return
        t = self._stack[-1]
        if tag == "table":
            self.tables.append(self._stack.pop())
        elif tag == "tr":
            t.end_row()
        elif tag in ("td", "th"):
            cell = getattr(t, "_pending_cell", None)
            if cell is not None and getattr(t, "_cell_open", False):
                t.add_cell(cell["text"], cell["colspan"], cell["rowspan"])
                t._cell_open = False

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_table:
            t = self._stack[-1]
            cell = getattr(t, "_pending_cell", None)
            if cell is not None and getattr(t, "_cell_open", False):
                cell["text"].append(data)

    def close(self):
        super().close()
        # 容错：未闭合的标签收尾
        while self._stack:
            self.tables.append(self._stack.pop())


def main():
    ap = argparse.ArgumentParser(description="抽取 HTML 中所有表格并各存为一个 CSV")
    ap.add_argument("input", help="输入 HTML 文件")
    ap.add_argument("-o", "--outdir", default=None, help="输出目录（默认与输入文件同目录）")
    ap.add_argument("--encoding", default="utf-8", help="输入文件编码（默认 utf-8）")
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        print(f"错误: 找不到输入文件 {args.input}", file=sys.stderr)
        return 2

    with open(args.input, "r", encoding=args.encoding, errors="replace") as f:
        html = f.read()

    p = TableExtractor()
    try:
        p.feed(html)
        p.close()
    except Exception as e:
        print(f"错误: 解析 HTML 失败: {e}", file=sys.stderr)
        return 1

    outdir = args.outdir or os.path.dirname(os.path.abspath(args.input))
    os.makedirs(outdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.input))[0]

    if not p.tables:
        print("未发现任何表格。")
        return 0

    written = []
    for i, t in enumerate(p.tables, 1):
        grid = t.finalize()
        path = os.path.join(outdir, f"{base}_table{i}.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows(grid)
        written.append(path)
        print(f"表格 {i}: {len(grid)} 行 x {len(grid[0]) if grid else 0} 列 -> {path}")
    print(f"完成，共 {len(written)} 个表格。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
