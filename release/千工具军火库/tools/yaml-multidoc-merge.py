#!/usr/bin/env python3
"""yaml-multidoc-merge —— 把多个 YAML 文件按命令行顺序合并成
一个 --- 分隔的多文档流。

每个文件去掉开头连续的 --- / ... 文档标记行（--- 后同行内容会保留）
与首尾空行后按序拼接，文档之间插入 --- 分隔行；文件内部的 --- 标记
原样保留（因此也允许输入本身是多文档流）。空文件跳过。纯文本级合并，
不解析 YAML 语义，不依赖 PyYAML；与 yaml-multidoc-split 互为逆操作。

示例:
  python yaml-multidoc-merge.py a.yaml b.yaml c.yaml -o bundle.yaml
  python yaml-multidoc-merge.py parts/*.yaml > bundle.yaml
  python yaml-multidoc-merge.py a.yaml b.yaml            # 直接打印到 stdout
"""
import argparse
import sys


def is_doc_start(body):
    return body == '---' or (body.startswith('---')
                             and len(body) > 3 and body[3] in ' \t')


def is_doc_end(body):
    return body == '...' or (body.startswith('...')
                             and len(body) > 3 and body[3] in ' \t')


def load_document(path):
    """读取一个文件，去掉头尾文档标记与首尾空行，返回文档文本。"""
    try:
        with open(path, encoding='utf-8-sig', newline='') as f:
            text = f.read()
    except OSError as exc:
        print(f'yaml-multidoc-merge: 无法读取 {path}: {exc}', file=sys.stderr)
        raise SystemExit(2)

    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1                                   # 跳过开头空行
    kept = []
    while i < len(lines):                        # 去掉开头连续的文档标记
        body = lines[i].rstrip('\r\n')
        if is_doc_start(body):
            rest = body[3:].strip()
            if rest and not rest.startswith('#'):
                kept.append(rest + lines[i][len(body):])
            i += 1
            continue
        if is_doc_end(body):
            i += 1
            continue
        break
    kept.extend(lines[i:])
    while kept and not kept[-1].strip():         # 去掉尾部空行
        kept.pop()
    while kept and is_doc_end(kept[-1].rstrip('\r\n')):
        kept.pop()                               # 去掉尾部的 ... 标记
    while kept and not kept[-1].strip():
        kept.pop()
    doc = ''.join(kept)
    if doc and not doc.endswith('\n'):
        doc += '\n'
    return doc


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='yaml-multidoc-merge',
        description='把多个 YAML 文件按顺序合并成 --- 分隔的多文档流')
    parser.add_argument('inputs', nargs='+', help='按合并顺序的 YAML 文件')
    parser.add_argument('-o', '--output', help='输出文件（缺省写 stdout）')
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', newline='')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

    docs = []
    for path in args.inputs:
        doc = load_document(path)
        if doc.strip():
            docs.append(doc)
    if not docs:
        print('yaml-multidoc-merge: 没有可合并的非空文档', file=sys.stderr)
        return 1

    chunks = []
    for i, doc in enumerate(docs):
        if i:
            chunks.append('---\n')
        chunks.append(doc)
    merged = ''.join(chunks)

    if args.output:
        try:
            with open(args.output, 'w', encoding='utf-8', newline='') as f:
                f.write(merged)
        except OSError as exc:
            print(f'yaml-multidoc-merge: 无法写出 {args.output}: {exc}',
                  file=sys.stderr)
            return 2
        print(f'已合并 {len(docs)} 个文档 -> {args.output}')
    else:
        sys.stdout.write(merged)
    return 0


if __name__ == '__main__':
    sys.exit(main())
