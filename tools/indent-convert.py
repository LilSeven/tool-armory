#!/usr/bin/env python3
"""缩进转换(indent-convert)

在制表符与指定宽度空格缩进之间转换,并正确处理续行对齐:
首行缩进按 tab 位数转换;续行(参数对齐、注释对齐等)中 tab 之后的
空格按制表位对齐补齐,保证转换后视觉列位置不变。

用法:
  python indent-convert.py <输入> --to spaces --width 4 [-o 输出]
  python indent-convert.py <输入> --to tabs --width 4 [-o 输出]
  cat in.txt | python indent-convert.py --to spaces

示例:
  python indent-convert.py code.py --to spaces --width 4 -o code4.py
  python indent-convert.py code4.py --to tabs --width 4
"""
import argparse
import sys


def line_to_spaces(line, width):
    """把行内 tab 展开为空格(按制表位展开,保持列位置)。"""
    out = []
    col = 0
    for ch in line:
        if ch == '\t':
            step = width - (col % width)
            out.append(' ' * step)
            col += step
        else:
            out.append(ch)
            col += 1
    return ''.join(out)


def line_to_tabs(line, width):
    """把行首(以及对齐段)的空格压缩为 tab,按制表位对齐。"""
    # 仅处理行首缩进;先量出缩进列 = 第一个非空白字符前的空格数
    stripped = line.lstrip(' ')
    n_indent = len(line) - len(stripped)
    tabs = (n_indent // width) * '\t' + ' ' * (n_indent % width)
    # 行中续行对齐的空格也尽量压缩(仅当整段空格落在制表位边界)
    body = []
    col = n_indent  # 折算后的起始列
    pending_spaces = 0
    for ch in stripped:
        if ch == '\t':
            if pending_spaces:
                body.append(' ' * pending_spaces)
                col += pending_spaces
                pending_spaces = 0
            body.append('\t')
            col += width - (col % width)
        elif ch == ' ':
            pending_spaces += 1
        else:
            if pending_spaces:
                # 若这串空格能凑满制表位则用 tab
                tabs_fit = (col % width == 0) and pending_spaces >= width
                if tabs_fit:
                    body.append('\t' * (pending_spaces // width))
                    body.append(' ' * (pending_spaces % width))
                else:
                    body.append(' ' * pending_spaces)
                col += pending_spaces
                pending_spaces = 0
            body.append(ch)
            col += 1
    if pending_spaces:
        # 行尾空白:保留为 tab 压缩形式
        if col % width == 0 and pending_spaces >= width:
            body.append('\t' * (pending_spaces // width) + ' ' * (pending_spaces % width))
        else:
            body.append(' ' * pending_spaces)
    return tabs + ''.join(body)


def convert(text, to, width):
    out_lines = []
    for line in text.splitlines():
        if to == 'spaces':
            out_lines.append(line_to_spaces(line, width))
        else:
            out_lines.append(line_to_tabs(line, width))
    return '\n'.join(out_lines) + ('\n' if text.endswith('\n') or out_lines else '')


def main(argv=None):
    # Windows 管道下 stdin 默认用本地 ANSI 代码页(如 GBK),显式按 UTF-8 读入
    if hasattr(sys.stdin, 'reconfigure'):
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description='在 tab 与指定宽度空格缩进之间转换')
    ap.add_argument('input', nargs='?', help='输入文件;缺省或 - 读 stdin')
    ap.add_argument('--to', required=True, choices=['tabs', 'spaces'])
    ap.add_argument('--width', type=int, default=4, help='tab 宽度(默认 4)')
    ap.add_argument('-o', '--output', help='输出文件;默认 stdout')
    args = ap.parse_args(argv)

    if args.width < 1:
        print('错误: --width 必须 >= 1', file=sys.stderr)
        return 2

    if args.input and args.input != '-':
        with open(args.input, encoding='utf-8', newline='') as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    result = convert(text, args.to, args.width)
    if args.output:
        with open(args.output, 'w', encoding='utf-8', newline='') as f:
            f.write(result)
        print(f'已写入 {args.output}')
    else:
        sys.stdout.write(result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
