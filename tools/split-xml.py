#!/usr/bin/env python3
"""XML 按元素拆分：把含大量重复子元素的 XML 按指定标签拆成多个片段文件，各自带根元素包装。

用 xml.etree.ElementTree 解析（仅适合常规大小文件），把根下所有匹配标签的
子元素逐个写出为独立片段文件，每个片段用原根元素（可带属性）包装，保持
命名空间声明可用。--chunk N 可把多个元素合进一个片段。

用法:
    python split-xml.py big.xml -t item -o out_dir/
    python split-xml.py big.xml -t item -o out_dir/ --chunk 100 --prefix part

参数:
    input        输入 XML 文件
    -t, --tag    要拆出的子元素标签名（必填）
    -o, --outdir 输出目录（默认在输入文件旁建 <名>_parts/）
    --chunk      每个片段包含的元素个数（默认 1）
    --prefix     片段文件名前缀（默认取标签名）

示例:
    python split-xml.py catalog.xml -t book -o parts/
    # 生成 parts/book_0001.xml 等，每个内容形如
    # <catalog xmlns="...">...<book>...</book>...</catalog>
"""
import argparse
import os
import sys
import xml.etree.ElementTree as ET


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def main(argv=None):
    ap = argparse.ArgumentParser(description="按标签把 XML 拆成带根包装的片段文件")
    ap.add_argument("input", help="输入 XML 文件")
    ap.add_argument("-t", "--tag", required=True, help="要拆出的子元素标签名（不含命名空间前缀）")
    ap.add_argument("-o", "--outdir", help="输出目录（默认 <输入名>_parts/）")
    ap.add_argument("--chunk", type=int, default=1, help="每片段元素数（默认 1）")
    ap.add_argument("--prefix", default=None, help="片段文件名前缀（默认标签名）")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.input):
        print(f"错误: 找不到输入文件 {args.input}", file=sys.stderr)
        return 1
    if args.chunk < 1:
        print("错误: --chunk 必须 >= 1", file=sys.stderr)
        return 1

    tree = ET.parse(args.input)
    root = tree.getroot()
    matches = [el for el in root if local_name(el.tag) == args.tag]
    if not matches:
        print(f"错误: 根元素 <{local_name(root.tag)}> 下没有 <{args.tag}> 子元素",
              file=sys.stderr)
        return 1

    outdir = args.outdir or (os.path.splitext(args.input)[0] + "_parts")
    os.makedirs(outdir, exist_ok=True)
    prefix = args.prefix or args.tag

    # 根包装：保留标签名与属性（含 xmlns 声明，ElementTree 存于 attrib）
    def wrap(children):
        r = ET.Element(root.tag, dict(root.attrib))
        for c in children:
            r.append(c)
        return ET.ElementTree(r)

    n_files = 0
    for i in range(0, len(matches), args.chunk):
        group = matches[i:i + args.chunk]
        path = os.path.join(outdir, f"{prefix}_{i // args.chunk + 1:04d}.xml")
        wrap(group).write(path, encoding="utf-8", xml_declaration=True)
        n_files += 1

    print(f"拆出 {len(matches)} 个 <{args.tag}>，生成 {n_files} 个片段 -> {outdir}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
