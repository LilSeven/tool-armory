"""CSV 行过滤：按列值条件（等于、包含、正则、数值比较）筛选行输出，支持多条件与取反。

仅使用 Python 标准库。--where 指定条件，格式 "列:操作:值"，可多次使用（AND 关系）；
操作: eq(等于) / ne(不等于) / contains(包含) / regex(正则) / lt le gt ge(数值比较)；
--invert 对整个条件组取反；列可用名称或 1 基序号；默认输出到 stdout。

示例:
  python csv-rows-filter.py data.csv --where "score:ge:80" --where "name:contains:张"
  python csv-rows-filter.py data.csv --where "id:regex:^A[0-9]+$" -o out.csv
  python csv-rows-filter.py data.csv --where "status:eq:done" --invert
"""
import argparse
import csv
import operator
import re
import sys
from pathlib import Path

NUM_OPS = {"lt": operator.lt, "le": operator.le,
           "gt": operator.gt, "ge": operator.ge}


def resolve(col, headers):
    if col.isdigit():
        i = int(col)
        if not 1 <= i <= len(headers):
            raise SystemExit(f"错误: 序号 {i} 超出范围 1..{len(headers)}")
        return i - 1
    try:
        return headers.index(col)
    except ValueError:
        raise SystemExit(f"错误: 找不到列 '{col}'，可用列: {headers}")


def build_predicate(spec, headers):
    try:
        col, op, value = spec.split(":", 2)
    except ValueError:
        raise SystemExit(f"错误: 条件需为 列:操作:值 格式，得到 '{spec}'")
    i = resolve(col, headers)
    if op in ("eq", "ne"):
        return (lambda row: (row[i] == value) == (op == "eq"))
    if op == "contains":
        return (lambda row: value in row[i])
    if op == "regex":
        try:
            rx = re.compile(value)
        except re.error as e:
            raise SystemExit(f"错误: 无效正则 '{value}': {e}")
        return (lambda row: rx.search(row[i]) is not None)
    if op in NUM_OPS:
        fn = NUM_OPS[op]
        try:
            num = float(value)
        except ValueError:
            raise SystemExit(f"错误: 数值比较需要数字，得到 '{value}'")

        def to_num(s):
            try:
                return float(s)
            except ValueError:
                return None
        return (lambda row: to_num(row[i]) is not None and fn(to_num(row[i]), num))
    raise SystemExit(f"错误: 未知操作 '{op}'，可用: eq ne contains regex lt le gt ge")


def main():
    p = argparse.ArgumentParser(description="CSV 行条件过滤")
    p.add_argument("input", help="输入 CSV 文件")
    p.add_argument("--where", action="append", default=[], metavar="列:操作:值",
                   help="筛选条件，可多次使用（AND 关系）")
    p.add_argument("--invert", action="store_true", help="取反：输出不满足条件的行")
    p.add_argument("-o", "--output", help="输出文件（默认 stdout）")
    p.add_argument("--no-header", action="store_true", help="输入无表头行")
    args = p.parse_args()

    if not args.where:
        raise SystemExit("错误: 至少需要一个 --where 条件")

    src = Path(args.input)
    if not src.is_file():
        raise SystemExit(f"错误: 输入文件不存在: {src}")
    with src.open("r", newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        raise SystemExit("错误: 输入 CSV 为空")

    if args.no_header:
        headers = [f"col{i+1}" for i in range(len(rows[0]))]
        data, out_header = rows, None
    else:
        headers, data = rows[0], rows[1:]
        out_header = rows[0]

    preds = [build_predicate(w, headers) for w in args.where]
    kept = [r for r in data if all(pr(r) for pr in preds) != args.invert]

    out = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout
    try:
        w = csv.writer(out)
        if out_header is not None:
            w.writerow(out_header)
        w.writerows(kept)
    finally:
        if args.output:
            out.close()
    print(f"筛选完成: {len(kept)}/{len(data)} 行"
          + (f"，输出 {args.output}" if args.output else ""),
          file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
