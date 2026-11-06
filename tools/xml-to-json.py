#!/usr/bin/env python3
"""XML 转 JSON —— 用 ElementTree 把 XML 展开为嵌套 JSON。

用法:
    python xml-to-json.py input.xml -o output.json
    python xml-to-json.py input.xml               # 缺省输出到 stdout

示例命令:
    python xml-to-json.py config.xml -o config.json
    python xml-to-json.py config.xml --indent 4

规则:
    - XML 属性转为 "@name" 键。
    - 同名重复子元素聚合为数组。
    - 元素文本放入 "#text" 键；若元素仅有文本（无属性、无子元素），直接输出字符串。
    - 空元素输出 null。
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET


def elem_to_obj(elem):
    """把一个 Element 递归展开为 dict / str / None。"""
    obj = {}
    for k, v in elem.attrib.items():
        obj[f"@{k}"] = v

    for child in elem:
        val = elem_to_obj(child)
        tag = child.tag
        if tag in obj:
            if not isinstance(obj[tag], list):
                obj[tag] = [obj[tag]]
            obj[tag].append(val)
        else:
            obj[tag] = val

    text = (elem.text or "").strip()
    if text:
        obj["#text"] = text

    if not obj:
        return None
    if len(obj) == 1 and "#text" in obj:
        return obj["#text"]
    return obj


def main(argv=None):
    ap = argparse.ArgumentParser(description="XML -> JSON（属性加 @ 前缀，重复子元素聚为数组）")
    ap.add_argument("input", help="输入 XML 文件路径")
    ap.add_argument("-o", "--output", help="输出 JSON 路径，缺省 stdout")
    ap.add_argument("--indent", type=int, default=2, help="JSON 缩进，0 表示单行")
    args = ap.parse_args(argv)

    try:
        tree = ET.parse(args.input)
    except (OSError, ET.ParseError) as e:
        print(f"错误: 解析 XML 失败: {e}", file=sys.stderr)
        return 2

    root = tree.getroot()
    data = {root.tag: elem_to_obj(root)}

    dump_kw = {"ensure_ascii": False, "indent": args.indent or None}
    text = json.dumps(data, **dump_kw)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
