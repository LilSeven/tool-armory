#!/usr/bin/env python3
"""yaml-multidoc-split —— 把含 --- 分隔的多文档 YAML 拆成单文档文件。

按 YAML 规范只把第 0 列的 --- 行（或 --- 后跟同行内容）当作文档开始
分隔符：块标量（| / >）中缩进的 --- 不会被误切；第 0 列的 ... 文档
结束标记被丢弃；空文档跳过；%YAML 等指令行保留给其后第一个文档。
输出按序号命名 outdir/prefix-001.ext …。纯文本级拆分，不解析 YAML
语义，不依赖 PyYAML。

示例:
  python yaml-multidoc-split.py bundle.yaml              # 拆到 bundle_split/
  python yaml-multidoc-split.py bundle.yaml -o parts/
  python yaml-multidoc-split.py b.yaml --prefix kube --ext yml

选项:
  -o, --output-dir DIR  输出目录（缺省为输入文件同目录下 <名字>_split）
  --prefix NAME         输出文件名前缀（缺省为输入文件主名）
  --ext EXT             输出扩展名（默认 yaml）
  --width N             序号补零位数（默认 3，不够时自动加宽）
"""
import argparse
import os
import re
import sys

DOC_START_RE = re.compile(r'^---($|[ \t])')   # 第 0 列文档开始标记
DOC_END_RE = re.compile(r'^\.\.\.($|[ \t])')  # 第 0 列文档结束标记


def tidy(lines):
    """去掉首尾空白行，保证以换行结尾。"""
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    text = ''.join(lines)
    if text and not text.endswith('\n'):
        text += '\n'
    return text


def split_documents(text):
    """返回单文档文本列表（空文档已剔除）。"""
    docs = []
    current = []

    def flush():
        # 只含 %YAML 指令行的块不单独成文档，留给下一个文档
        if any(l.strip() and not l.lstrip().startswith('%') for l in current):
            docs.append(''.join(current))
            current.clear()

    for line in text.splitlines(keepends=True):
        body = line.rstrip('\r\n')
        ending = line[len(body):]
        if DOC_START_RE.match(body):
            flush()
            rest = body[3:].strip()
            if rest and not rest.startswith('#'):
                current.append(rest + ending)   # --- 与文档内容同行
            continue
        if DOC_END_RE.match(body):
            continue
        current.append(line)
    flush()
    result = []
    for chunk in docs:
        cleaned = tidy(chunk.splitlines(keepends=True))
        if cleaned:
            result.append(cleaned)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='yaml-multidoc-split',
        description='把含 --- 分隔的多文档 YAML 拆成按序号命名的单文档文件')
    parser.add_argument('input', help='多文档 YAML 文件')
    parser.add_argument('-o', '--output-dir',
                        help='输出目录（缺省 <输入主名>_split）')
    parser.add_argument('--prefix', help='输出文件名前缀（缺省输入主名）')
    parser.add_argument('--ext', default='yaml', help='输出扩展名（默认 yaml）')
    parser.add_argument('--width', type=int, default=3, help='序号补零位数')
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', newline='')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

    try:
        with open(args.input, encoding='utf-8-sig', newline='') as f:
            text = f.read()
    except OSError as exc:
        print(f'yaml-multidoc-split: 无法读取 {args.input}: {exc}',
              file=sys.stderr)
        return 2

    docs = split_documents(text)
    if not docs:
        print(f'yaml-multidoc-split: {args.input} 中没有找到任何文档',
              file=sys.stderr)
        return 1

    stem = os.path.splitext(os.path.basename(args.input))[0]
    base_dir = os.path.dirname(os.path.abspath(args.input))
    outdir = args.output_dir or os.path.join(base_dir, stem + '_split')
    prefix = args.prefix or stem
    try:
        os.makedirs(outdir, exist_ok=True)
    except OSError as exc:
        print(f'yaml-multidoc-split: 无法创建目录 {outdir}: {exc}',
              file=sys.stderr)
        return 2

    width = max(args.width, len(str(len(docs))))
    written = []
    for idx, doc in enumerate(docs, 1):
        path = os.path.join(outdir,
                            f'{prefix}-{idx:0{width}d}.{args.ext.lstrip(".")}')
        try:
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(doc)
        except OSError as exc:
            print(f'yaml-multidoc-split: 无法写出 {path}: {exc}',
                  file=sys.stderr)
            return 2
        written.append(path)

    for path in written:
        print(path)
    print(f'共 {len(written)} 个文档 -> {outdir}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
