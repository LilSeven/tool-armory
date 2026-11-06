# -*- coding: utf-8 -*-
"""JSONL 与 JSON 数组互转。

JSON Lines（每行一个 JSON 对象）与 JSON 数组之间双向转换，逐行解析，
坏行不中断，最后汇总报告行号与错误信息。

用法:
    python jsonl-convert.py data.jsonl -o out.json     # JSONL -> JSON 数组
    python jsonl-convert.py data.json  -o out.jsonl    # JSON -> JSONL
    python jsonl-convert.py data.jsonl --strict        # 遇坏行立即失败（退出码 1）

方向根据输入内容自动判断：输入含多个 JSONL 行（>1 行可解析或多行内容）按 JSONL 处理；
也可用 --to jsonl / --to json 显式指定。

示例:
    python jsonl-convert.py logs.jsonl -o logs.json
    python jsonl-convert.py users.json -o users.jsonl
"""
import argparse
import json
import sys
import io


def jsonl_to_json(text):
    items = []
    errors = []
    for lineno, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        try:
            items.append(json.loads(s))
        except ValueError as e:
            errors.append((lineno, str(e)))
    return items, errors


def json_to_jsonl(data):
    lines = []
    for i, item in enumerate(data):
        try:
            lines.append(json.dumps(item, ensure_ascii=False))
        except (TypeError, ValueError) as e:
            lines.append(None)
            return lines, [(i + 1, str(e))]
    return lines, []


def main():
    ap = argparse.ArgumentParser(description="JSONL 与 JSON 数组双向转换，坏行容错报告")
    ap.add_argument("input", help="输入文件（.jsonl 或 .json）")
    ap.add_argument("-o", "--output", help="输出文件（缺省打印到 stdout）")
    ap.add_argument("--to", choices=["json", "jsonl"], default=None,
                    help="显式指定输出格式（缺省自动判断）")
    ap.add_argument("-e", "--encoding", default="utf-8-sig", help="输入编码")
    ap.add_argument("--strict", action="store_true", help="遇到坏行立即失败")
    args = ap.parse_args()

    with io.open(args.input, "r", encoding=args.encoding) as f:
        text = f.read()

    # 判断方向
    to = args.to
    if to is None:
        stripped = text.strip()
        if stripped.startswith("["):
            to = "jsonl"
        else:
            to = "json"

    if to == "json":
        items, errors = jsonl_to_json(text)
        if args.strict and errors:
            for lineno, msg in errors:
                print("坏行 %d: %s" % (lineno, msg), file=sys.stderr)
            return 1
        out_text = json.dumps(items, ensure_ascii=False, indent=2)
    else:
        try:
            data = json.loads(text)
        except ValueError as e:
            print("错误：输入不是合法 JSON: %s" % e, file=sys.stderr)
            return 1
        if not isinstance(data, list):
            print("错误：JSON 转 JSONL 需要 JSON 数组", file=sys.stderr)
            return 1
        lines, errors = json_to_jsonl(data)
        if args.strict and errors:
            for lineno, msg in errors:
                print("坏项 %d: %s" % (lineno, msg), file=sys.stderr)
            return 1
        out_text = "\n".join(l for l in lines if l is not None) + ("\n" if lines else "")

    for lineno, msg in errors:
        print("警告 坏行 %d: %s" % (lineno, msg), file=sys.stderr)

    if args.output:
        with io.open(args.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(out_text + "\n")
        print("已写入 %s（方向 %s）" % (args.output, "JSONL->JSON" if to == "json" else "JSON->JSONL"))
    else:
        sys.stdout.buffer.write((out_text + "\n").encode("utf-8"))

    if errors:
        print("共 %d 个坏行被跳过" % len(errors), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
