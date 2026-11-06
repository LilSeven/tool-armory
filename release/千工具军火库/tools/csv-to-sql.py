#!/usr/bin/env python3
"""CSV 转 SQL 脚本 —— 把 CSV 生成 INSERT 语句脚本，支持指定表名、列名与 NULL 值、引号转义。

用法:
    python csv-to-sql.py data.csv -o out.sql --table users
    python csv-to-sql.py data.csv --table users --columns id,name,age --null NULL

示例命令:
    python csv-to-sql.py users.csv -o users.sql --table users --null NULL --schema public
    python csv-to-sql.py users.csv                 # 表名取文件名主干 users

规则:
    - 第一行视为表头（列名），除非用 --columns 显式指定（此时不跳过首行）。
    - 单引号按 SQL 标准翻倍转义（' -> ''）。
    - 单元格值等于 --null 指定的标记（默认 NULL，区分大小写可关）时输出 SQL NULL。
    - 每行数据一条 INSERT 语句，以分号结尾；默认输出 BEGIN/COMMIT 包裹。
"""
import argparse
import csv
import os
import sys


def sql_quote(value):
    return "'" + value.replace("'", "''") + "'"


def main(argv=None):
    ap = argparse.ArgumentParser(description="CSV -> INSERT 语句 SQL 脚本")
    ap.add_argument("input", help="输入 CSV 文件路径")
    ap.add_argument("-o", "--output", help="输出 SQL 路径，缺省 stdout")
    ap.add_argument("-t", "--table", help="目标表名（默认取输入文件名主干）")
    ap.add_argument("-c", "--columns", help="逗号分隔的列名列表（覆盖表头）")
    ap.add_argument("-n", "--null", default="NULL", help="表示 SQL NULL 的单元格标记（默认 NULL）")
    ap.add_argument("--no-null-token", action="store_true", help="禁用 NULL 标记，所有值按字面字符串")
    ap.add_argument("--schema", help="可选 schema 限定，如 public")
    ap.add_argument("--no-transaction", action="store_true", help="不输出 BEGIN/COMMIT")
    args = ap.parse_args(argv)

    table = args.table or os.path.splitext(os.path.basename(args.input))[0]
    full_table = f"{args.schema}.{table}" if args.schema else table

    columns = None
    if args.columns:
        columns = [c.strip() for c in args.columns.split(",") if c.strip()]

    null_token = None if args.no_null_token else args.null

    try:
        fin = open(args.input, "r", encoding="utf-8-sig", newline="")
    except OSError as e:
        print(f"错误: 无法读取 CSV: {e}", file=sys.stderr)
        return 2

    fout = open(args.output, "w", encoding="utf-8", newline="\n") if args.output else sys.stdout
    try:
        reader = csv.reader(fin)
        try:
            header = next(reader)
        except StopIteration:
            print("错误: CSV 为空", file=sys.stderr)
            return 2
        if columns is None:
            columns = [h.strip() for h in header]
        else:
            fin.seek(0)  # 指定列名时不跳过首行

        if not args.output and not args.no_transaction:
            pass  # stdout 时也照常输出事务包裹
        if not args.no_transaction:
            fout.write("BEGIN;\n")

        col_sql = ", ".join(columns)
        count = 0
        reader = csv.reader(fin)
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue  # 跳过空行
            values = []
            for i, cell in enumerate(row):
                if i >= len(columns):
                    break
                if null_token is not None and cell == null_token:
                    values.append("NULL")
                else:
                    values.append(sql_quote(cell))
            # 缺失的列补 NULL
            values += ["NULL"] * (len(columns) - len(values))
            fout.write(f"INSERT INTO {full_table} ({col_sql}) VALUES ({', '.join(values)});\n")
            count += 1

        if not args.no_transaction:
            fout.write("COMMIT;\n")
        print(f"-- 共生成 {count} 条 INSERT 语句，目标表 {full_table}", file=sys.stderr)
    finally:
        fin.close()
        if args.output:
            fout.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
