#!/usr/bin/env python3
"""tsv-csv-swap —— TSV 与 CSV 双向转换(纯标准库), 正确处理两者约定差异。

方向(--to):
    csv   输入按 TSV 读(无引号约定: 引号是普通字符), 输出按 CSV 写
          (RFC4180 习惯: 含逗号/引号/换行的字段自动加引号, 字段内引号翻倍);
    tsv   输入按 CSV 读(解析引号转义), 输出按 TSV 写(无引号约定);
    auto  默认, 按首个非空行是否含制表符判断输入是 TSV 还是 CSV。

规则差异的处理: TSV 无引号约定无法表示 字段内制表符/换行, 因此 CSV→TSV
遇到这类字段时报错退出(带行号), 而不是悄悄破坏数据; TSV→CSV 时引号一律
视为普通字符, 字段含逗号/引号/换行时由 CSV 引号转义接管。

示例:
    python -I tsv-csv-swap.py data.tsv --to csv -o out.csv
    python -I tsv-csv-swap.py data.csv --to tsv -o out.tsv
    python -I tsv-csv-swap.py mixed.txt                # auto 判断方向
    cat data.tsv | python -I tsv-csv-swap.py --to csv

退出码: 0 成功; 1 输入/转换错误(如字段含制表符无法写入 TSV); 2 用法错误。
"""

import argparse
import csv
import itertools
import sys


def _convert(source, direction, out):
    if direction == 'tsv2csv':
        # 读: TSV 无引号约定, 引号是普通字符; 写: CSV 自动引号转义
        reader = csv.reader(source, delimiter='\t', quoting=csv.QUOTE_NONE)
        writer = csv.writer(out, delimiter=',', lineterminator='\n')
        for row in reader:
            if row:
                writer.writerow(row)
    else:
        # 读: CSV 引号转义; 写: TSV 无引号约定 —— 校验后以制表符字面拼接,
        # 含 制表符/换行 的字段直接报错(绝不悄悄破坏数据)
        reader = csv.reader(source)
        lineno = 0
        for row in reader:
            lineno += 1
            if not row:
                continue
            for field in row:
                if '\t' in field or '\n' in field or '\r' in field:
                    raise ValueError(
                        'CSV→TSV 第 %d 行: 字段含制表符/换行符, '
                        'TSV 无引号约定无法无损表示: %r' % (lineno, field))
            out.write('\t'.join(row) + '\n')


def _reconfigure_streams():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except Exception:
            pass
    try:
        sys.stdout.reconfigure(newline='')
    except Exception:
        pass


def _open_input(path):
    if path in (None, '-'):
        return sys.stdin, False
    return open(path, 'r', encoding='utf-8-sig', newline=''), True


def _open_output(path):
    if path in (None, '-'):
        return sys.stdout, False
    return open(path, 'w', encoding='utf-8', newline=''), True


def main(argv=None):
    _reconfigure_streams()
    parser = argparse.ArgumentParser(
        prog='tsv-csv-swap',
        description='TSV 与 CSV 双向转换(纯标准库), 正确处理无引号/引号约定差异。')
    parser.add_argument('input', nargs='?', metavar='FILE',
                        help="输入文件; 缺省或 '-' 表示 stdin")
    parser.add_argument('--to', choices=('tsv', 'csv', 'auto'), default='auto',
                        help='目标格式; auto 按首个非空行是否含制表符判断(默认 auto)')
    parser.add_argument('-o', '--output', metavar='FILE',
                        help='输出文件; 缺省 stdout')
    args = parser.parse_args(argv)

    raw_fh, close_in = _open_input(args.input)
    try:
        if args.to == 'auto':
            # 偷看首个非空行决定方向, 已读出的行再接回数据流, stdin 也适用
            peek = []
            while True:
                line = raw_fh.readline()
                if not line:
                    break
                peek.append(line)
                if line.strip():
                    break
            direction = 'tsv2csv' if any('\t' in ln for ln in peek) else 'csv2tsv'
            source = itertools.chain(peek, raw_fh)
        else:
            direction = 'tsv2csv' if args.to == 'csv' else 'csv2tsv'
            source = raw_fh
        out, close_out = _open_output(args.output)
        try:
            _convert(source, direction, out)
        finally:
            if close_out:
                out.close()
    finally:
        if close_in:
            raw_fh.close()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
    except (ValueError, OSError, csv.Error) as exc:
        print('error: %s' % exc, file=sys.stderr)
        sys.exit(1)
