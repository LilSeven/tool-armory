# -*- coding: utf-8 -*-
"""JSON 转 CSV。

把 JSON 对象数组展平为 CSV：自动收集所有键作表头；
嵌套键用点号路径展平（如 {"a": {"b": 1}} -> a.b,1）。

用法:
    python json-to-csv.py input.json                # 输出到 stdout
    python json-to-csv.py input.json -o out.csv     # 输出到文件
    python json-to-csv.py input.json --no-flatten   # 不展平嵌套，转 JSON 字符串

示例:
    输入 a.json: [{"name": "Alice", "addr": {"city": "BJ"}}]
    输出 CSV:    name,addr.city
                 Alice,BJ
"""
import argparse
import csv
import json
import sys
import io


def flatten(obj, prefix="", out=None):
    """把嵌套 dict 展平为点号路径键。列表等非 dict 值转 JSON 字符串。"""
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = "%s.%s" % (prefix, k) if prefix else str(k)
            flatten(v, path, out)
    else:
        if isinstance(obj, (list, tuple)):
            val = json.dumps(obj, ensure_ascii=False)
        elif obj is None:
            val = ""
        elif obj is True:
            val = "true"
        elif obj is False:
            val = "false"
        else:
            val = str(obj)
        out[prefix] = val
    return out


def collect_keys(rows):
    keys = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    return keys


def main():
    ap = argparse.ArgumentParser(description="JSON 对象数组转 CSV（嵌套键点号展平）")
    ap.add_argument("input", help="输入 JSON 文件（对象数组）")
    ap.add_argument("-o", "--output", help="输出 CSV 文件（缺省打印到 stdout）")
    ap.add_argument("-e", "--encoding", default="utf-8", help="输入编码（默认 utf-8）")
    ap.add_argument("--no-flatten", action="store_true", help="不展平嵌套对象，整体转 JSON 字符串")
    args = ap.parse_args()

    with io.open(args.input, "r", encoding=args.encoding) as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("错误：输入必须是 JSON 数组", file=sys.stderr)
        return 1

    if args.no_flatten:
        rows = [{k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list))
                     else ("" if v is None else ("true" if v is True else "false" if v is False else str(v))))
                 for k, v in item.items()} if isinstance(item, dict) else {}
                for item in data]
    else:
        rows = [flatten(item) if isinstance(item, dict) else {} for item in data]

    keys = collect_keys(rows)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=keys, extrasaction="ignore",
                            lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

    if args.output:
        with io.open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(buf.getvalue())
        print("已写入 %s（%d 条记录，%d 列）" % (args.output, len(rows), len(keys)))
    else:
        sys.stdout.buffer.write(buf.getvalue().encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
