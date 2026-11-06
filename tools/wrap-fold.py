#!/usr/bin/env python3
"""自动换行折叠(wrap-fold)

按显示宽度把长段落折叠为指定列宽:中文/全角字符算 2 格,ASCII 算 1 格,
支持悬挂缩进(续行缩进列数)。逐段处理,段内已换行视为硬换行;
也可以选择不重排已有换行(默认按段落合并后再折)。

用法:
  python wrap-fold.py <输入> [--width 40] [--hang 4] [-o 输出]
  cat in.txt | python wrap-fold.py --width 60

选项:
  --width N     目标列宽(默认 40)
  --hang N      悬挂缩进的列数(默认 4);0 表示续行从第 0 列开始
  --keep-breaks 不合并段落内已有换行,仅对超长行折叠
  --no-hang     等价于 --hang 0

示例:
  python wrap-fold.py doc.txt --width 40 --hang 4
  python wrap-fold.py notes.txt --width 60 --keep-breaks
"""
import argparse
import sys
import unicodedata


def display_width(s):
    """字符串显示宽度:East Asian Wide/Fullwidth 及控制补零计 2,其余计 1。"""
    w = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ('W', 'F'):
            w += 2
        else:
            w += 1
    return w


def fold_line(line, width, hang):
    """把单行按显示宽度折叠,返回行列表(含悬挂缩进)。"""
    if display_width(line) <= width:
        return [line]
    rows = []
    cur = []
    cur_w = 0
    for ch in line:
        cw = 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
        limit = width if not rows else width - hang
        if cur_w + cw > max(limit, 1):
            rows.append(''.join(cur))
            cur = []
            cur_w = 0
        cur.append(ch)
        cur_w += cw
    if cur:
        rows.append(''.join(cur))
    return rows


def fold_paragraph(text, width, hang, keep_breaks):
    paras = []
    if keep_breaks:
        paras = text.split('\n')
    else:
        # 按空行分段的经典处理:把同段的多行合并为一行
        buf = []
        for ln in text.split('\n'):
            if ln.strip() == '':
                if buf:
                    paras.append(' '.join(b.strip() for b in buf))
                    buf = []
                paras.append('')
            else:
                buf.append(ln)
        if buf:
            paras.append(' '.join(b.strip() for b in buf))

    out = []
    for para in paras:
        if para == '':
            out.append('')
            continue
        rows = fold_line(para, width, hang)
        for i, row in enumerate(rows):
            if i > 0 and hang > 0:
                out.append(' ' * hang + row)
            else:
                out.append(row)
    return '\n'.join(out)


def main(argv=None):
    # Windows 管道下 stdin 默认用本地 ANSI 代码页(如 GBK),显式按 UTF-8 读入
    if hasattr(sys.stdin, 'reconfigure'):
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description='按显示宽度(中文算 2 格)折叠长段落,支持悬挂缩进')
    ap.add_argument('input', nargs='?', help='输入文件;缺省或 - 读 stdin')
    ap.add_argument('--width', type=int, default=40, help='目标列宽(默认 40)')
    ap.add_argument('--hang', type=int, default=4, help='悬挂缩进列数(默认 4)')
    ap.add_argument('--no-hang', action='store_true', help='续行不缩进(等价 --hang 0)')
    ap.add_argument('--keep-breaks', action='store_true', help='不合并段落内换行,仅折叠超长行')
    ap.add_argument('-o', '--output', help='输出文件;默认 stdout')
    args = ap.parse_args(argv)

    if args.width < 2:
        print('错误: --width 必须 >= 2', file=sys.stderr)
        return 2
    hang = 0 if args.no_hang else max(args.hang, 0)
    if hang >= args.width:
        print('错误: --hang 必须小于 --width', file=sys.stderr)
        return 2

    if args.input and args.input != '-':
        with open(args.input, encoding='utf-8-sig') as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    result = fold_paragraph(text, args.width, hang, args.keep_breaks)
    result += '\n'
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f'已写入 {args.output}')
    else:
        sys.stdout.write(result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
