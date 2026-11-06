#!/usr/bin/env python3
"""XML 转 JSON — 用 ElementTree 把 XML 元素树转成保留属性与文本的 JSON 结构。

把 XML 文档转换为 JSON 对象：元素标签映射为 "tag"，属性放入 "attrs"，
文本内容放入 "text"（首尾空白被去除），子元素放入 "children" 列表。
只使用 Python 标准库（xml.etree.ElementTree / json / argparse）。

用法:
    python xml2json.py input.xml                 # 输出到 stdout
    python xml2json.py input.xml -o out.json     # 输出到文件
    python xml2json.py -e "<a x='1'>hi<b/></a>"  # 直接转换内联 XML 字符串

示例:
    $ python xml2json.py -e "<root id='1'><item>a</item></root>"
    {"tag": "root", "attrs": {"id": "1"}, "text": "", "children": [
        {"tag": "item", "attrs": {}, "text": "a", "children": []}]}
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET


def elem_to_dict(elem):
    """把一个 Element 递归转换为 dict: tag / attrs / text / children。"""
    return {
        "tag": elem.tag,
        "attrs": dict(elem.attrib),
        "text": (elem.text or "").strip(),
        "children": [elem_to_dict(child) for child in elem],
    }


def xml_to_json(xml_source, indent=2):
    """xml_source 可以是文件路径或内联 XML 字符串，返回格式化 JSON 字符串。"""
    if "<" in xml_source:
        root = ET.fromstring(xml_source)
    else:
        tree = ET.parse(xml_source)
        root = tree.getroot()
    return json.dumps(elem_to_dict(root), ensure_ascii=False, indent=indent)


def main(argv=None):
    parser = argparse.ArgumentParser(description="用 ElementTree 把 XML 转成保留属性与文本的 JSON")
    parser.add_argument("input", nargs="?", help="输入 XML 文件路径")
    parser.add_argument("-e", "--expr", help="内联 XML 字符串（与 input 二选一）")
    parser.add_argument("-o", "--output", help="输出 JSON 文件路径（缺省打印到 stdout）")
    args = parser.parse_args(argv)

    if bool(args.input) == bool(args.expr):
        parser.error("必须且只能提供 input 文件或 -e 内联字符串之一")

    try:
        result = xml_to_json(args.expr if args.expr else args.input)
    except ET.ParseError as exc:
        print(f"错误: XML 解析失败: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"错误: 读取文件失败: {exc}", file=sys.stderr)
        return 1

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(result + "\n")
        print(f"已写入 {args.output}")
    else:
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
