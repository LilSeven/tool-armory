"""CSV 列操作：按名称或序号选择、重排、重命名、删除 CSV 的列后输出新文件。

仅使用 Python 标准库。列可用名称（精确匹配）或 1 基序号（如 "3"）指定；
--keep 为白名单（按给定顺序重排），--drop 为黑名单，两者互斥；
--rename 格式 "旧:新"，可多次使用；默认覆盖写为 <输入名>_cols.csv。

示例:
  python csv-column-ops.py data.csv --keep "id,name,score"
  python csv-column-ops.py data.csv --drop 2 --rename "score:总分"
  python csv-column-ops.py data.csv --keep name,id -o out.csv
"""
import argparse
import csv
import sys
from pathlib import Path


def resolve(col, headers):
    """把列名或 1 基序号解析为表头索引。"""
    if col.isdigit():
        i = int(col)
        if not 1 <= i <= len(headers):
            raise SystemExit(f"错误: 序号 {i} 超出范围 1..{len(headers)}")
        return i - 1
    try:
        return headers.index(col)
    except ValueError:
        raise SystemExit(f"错误: 找不到列 '{col}'，可用列: {headers}")


def main():
    p = argparse.ArgumentParser(description="CSV 列选择/重排/重命名/删除")
    p.add_argument("input", help="输入 CSV 文件")
    p.add_argument("-o", "--output", help="输出文件（默认 <输入名>_cols.csv）")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--keep", help="保留的列，逗号分隔，按此顺序输出")
    g.add_argument("--drop", help="删除的列，逗号分隔")
    p.add_argument("--rename", action="append", default=[],
                   metavar="旧:新", help="重命名列，可多次使用")
    p.add_argument("--no-header", action="store_true", help="输入无表头行")
    args = p.parse_args()

    src = Path(args.input)
    if not src.is_file():
        raise SystemExit(f"错误: 输入文件不存在: {src}")
    dst = Path(args.output) if args.output else src.with_name(src.stem + "_cols.csv")

    with src.open("r", newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        raise SystemExit("错误: 输入 CSV 为空")

    if args.no_header:
        ncol = len(rows[0])
        headers = [f"col{i+1}" for i in range(ncol)]
        data = rows
    else:
        headers, data = rows[0], rows[1:]

    if args.keep:
        idx = [resolve(c, headers) for c in args.keep.split(",")]
    elif args.drop:
        dropped = {resolve(c, headers) for c in args.drop.split(",")}
        idx = [i for i in range(len(headers)) if i not in dropped]
        if not idx:
            raise SystemExit("错误: 不能删除所有列")
    else:
        idx = list(range(len(headers)))

    renames = {}
    for r in args.rename:
        if ":" not in r:
            raise SystemExit(f"错误: --rename 需为 旧:新 格式，得到 '{r}'")
        old, new = r.split(":", 1)
        renames[resolve(old, headers)] = new

    new_headers = [renames.get(i, headers[i]) for i in idx]
    with dst.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not args.no_header:
            w.writerow(new_headers)
        for row in data:
            w.writerow([row[i] if i < len(row) else "" for i in idx])

    action = "保留" if args.keep else ("删除" if args.drop else "复制")
    print(f"完成: {action} {len(idx)} 列，输出 {dst}（{len(data)} 行数据）")


if __name__ == "__main__":
    sys.exit(main())
