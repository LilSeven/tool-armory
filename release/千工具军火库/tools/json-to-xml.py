#!/usr/bin/env python3
"""JSON 转 XML —— 把 JSON 对象序列化为 XML 元素树，支持指定根元素名与数组重复元素。

用法:
    python json-to-xml.py input.json -o output.xml [--root rootname]
    python json-to-xml.py input.json              # 缺省输出到 stdout

示例命令:
    python json-to-xml.py config.json -o config.xml --root server
    python json-to-xml.py users.json --root users

规则:
    - JSON 对象的键转为同名子元素；值为数组时按数组元素重复同名子元素。
    - 以 "@" 开头的键转为父元素的属性，"#text" 键转为元素文本。
    - 嵌套对象递归展开；null 输出空元素；true/false 输出小写 true/false。
    - 顶层必须是 JSON 对象，包裹在 --root（默认 root）指定的根元素内。
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET


def scalar_text(value):
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return ""
    return str(value)


def add_child(parent, key, value):
    """把一个键值对挂到 parent 下；数组值重复同名子元素。"""
    if key.startswith("@"):
        if isinstance(value, (dict, list)):
            raise ValueError(f"属性 {key} 的值必须是标量，得到 {type(value).__name__}")
        parent.set(key[1:], scalar_text(value))
        return
    if key == "#text":
        parent.text = scalar_text(value)
        return
    if isinstance(value, list):
        for item in value:
            add_child(parent, key, item)
        return
    sub = ET.SubElement(parent, key)
    if isinstance(value, dict):
        for k, v in value.items():
            add_child(sub, k, v)
    else:
        sub.text = scalar_text(value)


def main(argv=None):
    ap = argparse.ArgumentParser(description="JSON -> XML（数组重复元素，可指定根元素名）")
    ap.add_argument("input", help="输入 JSON 文件路径")
    ap.add_argument("-o", "--output", help="输出 XML 路径，缺省 stdout")
    ap.add_argument("--root", default="root", help="根元素名（默认 root）")
    args = ap.parse_args(argv)

    try:
        with open(args.input, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"错误: 读取/解析 JSON 失败: {e}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print("错误: 顶层 JSON 必须是对象（dict）", file=sys.stderr)
        return 2

    root = ET.Element(args.root)
    try:
        for k, v in data.items():
            add_child(root, k, v)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2

    ET.indent(root, space="  ")
    xml_bytes = ET.tostring(root, encoding="unicode")
    text = f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_bytes}\n'

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
