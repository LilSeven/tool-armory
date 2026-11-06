"""CSV 列画像：推断每列类型、空值率、唯一值基数、最大最小值并输出数据概览报告。

功能：
  - 逐列推断类型（integer / float / boolean / date / string），支持混合类型标注
  - 统计空值率（空串与 --nulls 指定的占位符都算空）
  - 统计唯一值基数（unique）与唯一率
  - 数值/日期列给出 min/max，分类型展示；文本列给出最长值长度
  - 输出 Markdown 风格概览报告到 stdout（或 -o 指定文件）

示例命令：
  python csv-profile.py data.csv
  python csv-profile.py data.csv --delim ";" --nulls "N/A,NULL" --top 5
  python csv-profile.py data.csv -o report.md --encoding gbk

参数：
  file                 输入 CSV 文件路径
  --delim SEP          分隔符（默认逗号）
  --encoding ENC       输入编码（默认 utf-8-sig）
  --nulls LIST         额外空值占位符，逗号分隔（默认 NULL,N/A,na,null）
  --top N              每列展示前 N 个高频值（默认 3，0 关闭）
"""
import argparse
import csv
import re
import sys
from datetime import datetime
from collections import Counter

INT_RE = re.compile(r"^[+-]?\d+$")
FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
BOOL_SET = {"true", "false", "yes", "no", "t", "f", "y", "n", "1", "0"}
DATE_FMTS = ["%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S",
             "%d/%b/%Y", "%b %d, %Y", "%Y%m%d"]


def parse_date(s):
    for fmt in DATE_FMTS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def infer_cell(cell):
    """返回 (type, parsed_value)；type ∈ int/float/bool/date/str。"""
    if INT_RE.match(cell):
        return "int", int(cell)
    if FLOAT_RE.match(cell):
        return "float", float(cell)
    low = cell.lower()
    if low in BOOL_SET:
        return "bool", (low in ("true", "yes", "t", "y", "1"))
    d = parse_date(cell)
    if d is not None:
        return "date", d
    return "str", cell


def profile(path, args):
    nulls = set(x.strip() for x in args.nulls.split(",") if x.strip())
    with open(path, newline="", encoding=args.encoding) as f:
        reader = csv.reader(f, delimiter=args.delim)
        try:
            header = next(reader)
        except StopIteration:
            raise SystemExit("empty CSV: no header row")
        # 每列状态
        types = [dict() for _ in header]          # type -> count
        nulls_n = [0] * len(header)
        seen = [set() for _ in header]
        mins = [None] * len(header)
        maxs = [None] * len(header)
        minmax_type = [""] * len(header)
        str_maxlen = [0] * len(header)
        top_counter = [Counter() for _ in header]
        rows = 0

        for row in reader:
            if not row or (len(row) == 1 and not row[0].strip()):
                continue
            rows += 1
            for i, name in enumerate(header):
                cell = row[i].strip() if i < len(row) else ""
                if not cell or cell in nulls:
                    nulls_n[i] += 1
                    continue
                t, v = infer_cell(cell)
                types[i][t] = types[i].get(t, 0) + 1
                seen[i].add(cell)
                top_counter[i][cell] += 1
                if t in ("int", "float"):
                    key = v
                    if minmax_type[i] in ("", "num"):
                        mins[i] = key if mins[i] is None else min(mins[i], key)
                        maxs[i] = key if maxs[i] is None else max(maxs[i], key)
                        minmax_type[i] = "num"
                elif t == "date":
                    if minmax_type[i] in ("", "date"):
                        mins[i] = v if mins[i] is None else min(mins[i], v)
                        maxs[i] = v if maxs[i] is None else max(maxs[i], v)
                        minmax_type[i] = "date"
                else:
                    str_maxlen[i] = max(str_maxlen[i], len(cell))

    # 汇总输出
    lines = ["# CSV 列画像报告", "", f"- 文件：`{path}`", f"- 数据行数：{rows}",
             f"- 列数：{len(header)}", ""]
    lines.append("| 列名 | 类型 | 非空 | 空值率 | 唯一数 | 最小值 | 最大值 | 最长文本 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for i, name in enumerate(header):
        total = rows
        if types[i]:
            if len(types[i]) == 1:
                tcol = next(iter(types[i]))
            else:
                tcol = "mixed(" + ",".join(f"{k}x{v}" for k, v in
                                           sorted(types[i].items(), key=lambda x: -x[1])) + ")"
        else:
            tcol = "empty"
        null_rate = (nulls_n[i] / total * 100) if total else 0.0
        if minmax_type[i] == "num":
            mn, mx = str(mins[i]), str(maxs[i])
        elif minmax_type[i] == "date":
            mn, mx = mins[i].strftime("%Y-%m-%d %H:%M:%S"), maxs[i].strftime("%Y-%m-%d %H:%M:%S")
        else:
            mn = mx = "-"
        lines.append(f"| {name} | {tcol} | {total - nulls_n[i]} | {null_rate:.1f}% | "
                     f"{len(seen[i])} | {mn} | {mx} | {str_maxlen[i] or '-'} |")

    if args.top:
        lines.append("")
        lines.append("## 高频值 Top %d" % args.top)
        for i, name in enumerate(header):
            common = top_counter[i].most_common(args.top)
            if common:
                items = ", ".join(f"`{v}`x{c}" for v, c in common)
                lines.append(f"- **{name}**: {items}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="CSV 列画像：类型/空值率/基数/极值概览报告")
    ap.add_argument("file", help="输入 CSV 文件")
    ap.add_argument("--delim", default=",", help="分隔符（默认逗号）")
    ap.add_argument("--encoding", default="utf-8-sig", help="输入编码（默认 utf-8-sig）")
    ap.add_argument("--nulls", default="NULL,N/A,na,null", help="额外空值占位符，逗号分隔")
    ap.add_argument("--top", type=int, default=3, help="每列展示高频值个数（0 关闭）")
    ap.add_argument("-o", "--output", help="输出报告文件（默认 stdout）")
    args = ap.parse_args(argv)

    report = profile(args.file, args)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"report written: {args.output}")
    else:
        sys.stdout.write(report)


if __name__ == "__main__":
    main()
