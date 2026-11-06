# -*- coding: utf-8 -*-
"""CSV 转 JSON 数组。

把 CSV 转为 JSON 数组：首行作为键，后续每行生成一个对象。
支持整数/浮点/布尔类型推断开关（默认开启，可用 --no-infer 关闭）。

用法:
    python csv-to-json.py input.csv                 # 输出到 stdout
    python csv-to-json.py input.csv -o out.json     # 输出到文件
    python csv-to-json.py input.csv --no-infer      # 全部保持字符串
    python csv-to-json.py input.csv --delimiter ";" --encoding gbk

示例:
    输入 a.csv:  name,age,ok
                 Alice,30,true
    输出:        [{"name": "Alice", "age": 30, "ok": true}]
"""
import argparse
import csv
import json
import sys
import io


def infer(value):
    """字符串 -> int/float/bool，失败则原样返回字符串。"""
    v = value.strip()
    low = v.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(v)
    except ValueError:
        pass
    try:
        f = float(v)
        if v not in ("",) and not low.startswith("0x"):
            return f
    except ValueError:
        pass
    return value


def convert(reader, do_infer=True):
    rows = list(reader)
    if not rows:
        return []
    header = [h.strip() for h in rows[0]]
    out = []
    for row in rows[1:]:
        if not any(cell != "" for cell in row):
            continue  # 跳过空行
        obj = {}
        for i, key in enumerate(header):
            if not key:
                continue
            val = row[i] if i < len(row) else ""
            obj[key] = infer(val) if do_infer else val
        out.append(obj)
    return out


def main():
    ap = argparse.ArgumentParser(description="CSV 转 JSON 数组（首行作键）")
    ap.add_argument("input", help="输入 CSV 文件")
    ap.add_argument("-o", "--output", help="输出 JSON 文件（缺省打印到 stdout）")
    ap.add_argument("-d", "--delimiter", default=",", help="字段分隔符（默认逗号）")
    ap.add_argument("-e", "--encoding", default="utf-8-sig", help="输入编码（默认 utf-8-sig）")
    ap.add_argument("--no-infer", action="store_true", help="不做类型推断，全部输出字符串")
    ap.add_argument("--indent", type=int, default=None, help="JSON 缩进空格数")
    args = ap.parse_args()

    with io.open(args.input, "r", encoding=args.encoding, newline="") as f:
        reader = csv.reader(f, delimiter=args.delimiter)
        data = convert(reader, do_infer=not args.no_infer)

    text = json.dumps(data, ensure_ascii=False, indent=args.indent)
    if args.output:
        with io.open(args.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
        print("已写入 %s（%d 条记录）" % (args.output, len(data)))
    else:
        sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
