#!/usr/bin/env python3
"""pipe2csv —— 把竖线/多空格分隔的表格输出清洗成规范 CSV。

清洗 ps、df、kubectl get 等命令的表格输出（竖线分隔，或 column -t
产生的多空格对齐）：自动识别分隔方式，去掉表框行（+----+）、markdown
分隔行（| --- |）与首尾竖线，字段去首尾空白后用 csv 模块规范写出，
含逗号/引号/空格的字段自动加引号转义，首行保留为表头行。

示例:
  df -h | column -t | python pipe2csv.py > df.csv
  ps aux | column -t | python pipe2csv.py -o procs.csv
  python pipe2csv.py table.txt                 # 竖线/多空格自动识别
  python pipe2csv.py table.txt --sep space     # 强制按 2+ 空格切分
  python pipe2csv.py table.txt --sep pipe -d ';'

选项:
  -o, --output FILE   写入文件（缺省打印到 stdout）
  -s, --sep MODE      输入分隔方式 pipe|space|auto，默认 auto：
                      任一非空行含 | 则按竖线切分，否则按 2+ 空格切分
  -d, --delimiter CH  输出 CSV 字段分隔符，默认逗号
"""
import argparse
import csv
import re
import sys

BORDER_RE = re.compile(r'^\s*[+|][-=+|]*[+|]\s*$')   # 整行表框 +----+ / |---|
CELLSEP_RE = re.compile(r'^:?-+:?$')                 # markdown 单元格 --- / :---:


def split_pipe(line):
    """按竖线切分，去掉首尾竖线与字段两端空白。"""
    return [f.strip() for f in line.strip().strip('|').split('|')]


def split_space(line):
    """按 2 个以上空白（含 tab）切分，保留字段内的单个空格。"""
    return re.split(r'\s{2,}|\t+', line.strip())


def is_noise(fields):
    """全空行或 markdown 分隔行（每格都是 --- / :---:）视为噪音。"""
    if not any(fields):
        return True
    return all(CELLSEP_RE.match(f) for f in fields)


def clean_to_rows(text, mode):
    rows = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if BORDER_RE.match(raw):
            continue
        fields = split_pipe(raw) if mode == 'pipe' else split_space(raw)
        if not is_noise(fields):
            rows.append(fields)
    return rows


def detect_mode(lines):
    for line in lines:
        if line.strip() and '|' in line:
            return 'pipe'
    return 'space'


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='pipe2csv',
        description='把竖线/多空格分隔的命令表格输出清洗成规范 CSV')
    parser.add_argument('input', nargs='?', help='输入文件（缺省读 stdin）')
    parser.add_argument('-o', '--output', help='输出文件（缺省写 stdout）')
    parser.add_argument('-s', '--sep', choices=('pipe', 'space', 'auto'),
                        default='auto', help='输入分隔方式（默认 auto）')
    parser.add_argument('-d', '--delimiter', default=',',
                        help='输出 CSV 字段分隔符（默认逗号）')
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', newline='')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

    try:
        if args.input:
            with open(args.input, encoding='utf-8-sig', errors='replace',
                      newline='') as f:
                text = f.read()
        else:
            try:
                sys.stdin.reconfigure(encoding='utf-8', errors='replace')
            except (AttributeError, ValueError):
                pass
            text = sys.stdin.read()
    except OSError as exc:
        print(f'pipe2csv: 无法读取输入: {exc}', file=sys.stderr)
        return 2

    mode = args.sep
    if mode == 'auto':
        mode = detect_mode(text.splitlines())

    rows = clean_to_rows(text, mode)
    try:
        if args.output:
            with open(args.output, 'w', encoding='utf-8', newline='') as f:
                csv.writer(f, delimiter=args.delimiter,
                           lineterminator='\n').writerows(rows)
        else:
            csv.writer(sys.stdout, delimiter=args.delimiter,
                       lineterminator='\n').writerows(rows)
    except OSError as exc:
        print(f'pipe2csv: 无法写出: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
