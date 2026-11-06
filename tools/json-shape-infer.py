"""JSON 结构推断：扫描 JSON / JSONL 集合推断字段类型、可选性与嵌套结构摘要。

功能：
  - 支持 JSON 数组、JSONL（每行一个对象）、单个 JSON 对象
  - 汇总每个字段的类型分布（string/int/float/bool/null/array/object）、
    可选性（出现率 missing 率）以及枚举基数
  - 对嵌套对象/数组递归输出结构摘要（缩进树形），数组统计元素个数范围
  - 输出到 stdout 或 -o 文件，Markdown 风格

示例命令：
  python json-shape-infer.py records.jsonl
  python json-shape-infer.py data.json --max-depth 3
  python json-shape-infer.py data.jsonl -o shape.md

参数：
  file                 输入 .json 或 .jsonl 文件（按扩展名与内容自动识别）
  --max-depth N        嵌套展示最大深度（默认 4）
  --encoding ENC       输入编码（默认 utf-8）
"""
import argparse
import json
import sys
from collections import Counter


def type_name(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return "unknown"


def deep_scan(records, max_depth, depth=0, prefix=""):
    """递归扫描 dict 值，返回行列表（带层级）。"""
    lines = []
    if depth > max_depth:
        lines.append("  " * depth + "... (max depth reached)")
        return lines
    fields = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        for k, v in rec.items():
            fields.setdefault(k, []).append(v)
    for name in sorted(fields):
        vals = fields[name]
        tc = Counter(type_name(v) for v in vals)
        missing = len(records) - len(vals)
        miss_txt = f", missing {(missing / len(records) * 100):.1f}%" if records and missing else ""
        tdist = " ".join(f"{k}:{v}" for k, v in tc.most_common())
        scalars = [v for v in vals if isinstance(v, (str, int, float, bool))]
        uniq = set(str(v) for v in scalars)
        card = f", card={len(uniq)}" if uniq and len(uniq) <= 20 else ""
        lines.append("  " * depth + f"- {prefix}{name}: [{tdist}{miss_txt}{card}]")
        # 数组：取子元素扫
        arr_items = [x for v in vals if isinstance(v, list) for x in v]
        if arr_items and depth + 1 <= max_depth:
            lens = [len(v) for v in vals if isinstance(v, list)]
            if lens:
                lines.append("  " * (depth + 1) +
                             f"(array: n={len(lens)}, len {min(lens)}..{max(lens)}, items={len(arr_items)})")
            sub = deep_scan(arr_items, max_depth, depth + 2)
            lines.extend(sub)
        sub_objs = [v for v in vals if isinstance(v, dict)]
        if sub_objs and depth + 1 <= max_depth:
            lines.extend(deep_scan(sub_objs, max_depth, depth + 1))
    return lines


def load_records(path, encoding):
    with open(path, encoding=encoding) as f:
        text = f.read()
    stripped = text.lstrip()
    if path.lower().endswith(".jsonl"):
        recs = []
        for ln in text.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            recs.append(json.loads(ln))
        return recs
    data = json.loads(text)
    if isinstance(data, list):
        return data
    return [data]


def main(argv=None):
    ap = argparse.ArgumentParser(description="JSON/JSONL 字段类型、可选性与嵌套结构推断")
    ap.add_argument("file", help="输入 JSON / JSONL 文件")
    ap.add_argument("--max-depth", type=int, default=4, help="嵌套展示最大深度（默认 4）")
    ap.add_argument("--encoding", default="utf-8", help="输入编码")
    ap.add_argument("-o", "--output", help="输出文件（默认 stdout）")
    args = ap.parse_args(argv)

    records = load_records(args.file, args.encoding)
    n = len(records)
    lines = ["# JSON 结构推断报告", "", f"- 文件：`{args.file}`", f"- 记录数：{n}", "",
             "## 字段结构（层级缩进树）"]
    lines.extend(deep_scan(records, args.max_depth))
    report = "\n".join(lines) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"report written: {args.output}")
    else:
        sys.stdout.write(report)


if __name__ == "__main__":
    main()
