#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""csv-pk-diff.py —— CSV 按主键对比工具（仅用 Python 标准库）。

以主键列对齐两份 CSV，报告三类差异：
    + 新增记录（仅在新文件中出现）
    - 删除记录（仅在旧文件中出现）
    ~ 修改记录（主键相同但字段值不同，逐字段列出）

用途:
    对比用户表、商品表等按主键组织的 CSV 导出，找出增删改的记录。

示例命令:
    python csv-pk-diff.py old.csv new.csv --key id
    python csv-pk-diff.py old.csv new.csv --key id,name --delimiter ";"
    python csv-pk-diff.py old.csv new.csv --key id --max-report 20

选项:
    --key KEYS       主键列名，多个用逗号分隔（必填）
    --delimiter CHAR 字段分隔符（默认逗号）
    --max-report N   每类最多列出 N 条（默认 100，0=不限）

退出码:
    0 = 运行成功
    2 = 参数错误 / 文件读取失败 / 主键列不存在 / 主键值重复
"""

import argparse
import csv
import json
import sys


def setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def read_csv(path, delimiter):
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: 缺少表头行")
        return reader.fieldnames, list(reader)


def cell(row, col):
    value = row.get(col)
    return "" if value is None else value


def main(argv=None):
    setup_stdio()
    parser = argparse.ArgumentParser(
        description="按主键列比较两个 CSV，报告新增/删除/字段修改的记录。")
    parser.add_argument("old", help="旧 CSV 文件")
    parser.add_argument("new", help="新 CSV 文件")
    parser.add_argument("--key", required=True,
                        help="主键列名，多个用逗号分隔")
    parser.add_argument("--delimiter", default=",",
                        help="字段分隔符（默认逗号）")
    parser.add_argument("--max-report", type=int, default=100,
                        help="每类最多列出 N 条（0=不限，默认 100）")
    args = parser.parse_args(argv)

    keys = [k.strip() for k in args.key.split(",") if k.strip()]
    if not keys:
        print("错误: --key 不能为空", file=sys.stderr)
        return 2

    try:
        old_fields, old_rows = read_csv(args.old, args.delimiter)
        new_fields, new_rows = read_csv(args.new, args.delimiter)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    for col in keys:
        for label, fields in (("旧", old_fields), ("新", new_fields)):
            if col not in fields:
                print(f"错误: {label}文件缺少主键列 {col!r}", file=sys.stderr)
                return 2

    def index_rows(rows, label):
        table = {}
        for row in rows:
            k = tuple(cell(row, c) for c in keys)
            if k in table:
                print(f"错误: {label}文件中主键 {k} 重复", file=sys.stderr)
                return None
            table[k] = row
        return table

    old_table = index_rows(old_rows, "旧")
    new_table = index_rows(new_rows, "新")
    if old_table is None or new_table is None:
        return 2

    compare_cols = [c for c in old_fields
                    if c in new_fields and c not in keys]
    only_old_cols = [c for c in old_fields if c not in new_fields]
    only_new_cols = [c for c in new_fields if c not in old_fields]
    notes = []
    if only_old_cols:
        notes.append(f"仅旧文件有的列(不参与修改比较): {','.join(only_old_cols)}")
    if only_new_cols:
        notes.append(f"仅新文件有的列(不参与修改比较): {','.join(only_new_cols)}")
    if notes:
        print(f"提示: {'；'.join(notes)}")

    def show_row(row):
        meta = {c: cell(row, c) for c in row if c and c not in keys}
        return json.dumps(meta, ensure_ascii=False)

    added = sorted(k for k in new_table if k not in old_table)
    removed = sorted(k for k in old_table if k not in new_table)
    modified = []
    for k, row in new_table.items():
        if k not in old_table:
            continue
        field_diffs = [(c, cell(old_table[k], c), cell(row, c))
                       for c in compare_cols
                       if cell(old_table[k], c) != cell(row, c)]
        if field_diffs:
            modified.append((k, field_diffs))
    modified.sort(key=lambda item: item[0])

    lines = {
        "删除": [f"- [删除] {'='.join(k)}  {show_row(old_table[k])}"
                 for k in removed],
        "新增": [f"+ [新增] {'='.join(k)}  {show_row(new_table[k])}"
                 for k in added],
        "修改": [f"~ [修改] {'='.join(k)}  "
                 + "; ".join(f"{c}: {o} -> {n}" for c, o, n in diffs)
                 for k, diffs in modified],
    }
    for label in ("删除", "新增", "修改"):
        group = lines[label]
        cap = len(group) if args.max_report == 0 else args.max_report
        for line in group[:cap]:
            print(line)
        if len(group) > cap:
            print(f"  ...（{label}类还有 {len(group) - cap} 条未显示）")

    if not (added or removed or modified):
        print("两份 CSV 按主键对比完全一致。")
    print(f"摘要: 新增 {len(added)} 条, 删除 {len(removed)} 条, "
          f"修改 {len(modified)} 条（主键: {','.join(keys)}）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
