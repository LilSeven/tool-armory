#!/usr/bin/env python3
"""记录数组转 CSV (json-records2csv) —— 把 JSON 数组中的同构对象
按指定字段顺序（缺省按首个对象键序）展平导出为 CSV。

特性：
  - --fields a,b,c 指定并排序输出字段；缺失字段留空
  - 嵌套值（dict/list）自动序列化为 JSON 字符串
  - 标量数组或含非对象的数组会报错退出（exit 1）

用法:
    python json-records2csv.py 输入.json 输出.csv [--fields id,name]
示例:
    python json-records2csv.py users.json users.csv --fields id,name,email
"""

import argparse
import csv
import json
import sys


def cell(value):
    """把非标量值序列化为 JSON 字符串，其余原样。"""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def main(argv):
    ap = argparse.ArgumentParser(description="JSON 对象数组展平导出 CSV")
    ap.add_argument("src", help="输入 JSON 文件（对象数组）")
    ap.add_argument("dst", help="输出 CSV 文件")
    ap.add_argument("--fields", default="",
                    help="逗号分隔的字段顺序，如 id,name")
    args = ap.parse_args(argv[1:])

    with open(args.src, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("错误: 输入 JSON 顶层必须是数组", file=sys.stderr)
        return 1
    if any(not isinstance(rec, dict) for rec in data):
        print("错误: 数组中存在非对象元素", file=sys.stderr)
        return 1

    if args.fields:
        fields = [x.strip() for x in args.fields.split(",") if x.strip()]
    else:
        # 首个对象键序为默认字段序
        fields = list(data[0].keys()) if data else []

    with open(args.dst, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fields)
        for rec in data:
            writer.writerow([cell(rec.get(k)) for k in fields])
    print(f"导出 {len(data)} 条记录, {len(fields)} 个字段 -> {args.dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
