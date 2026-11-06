#!/usr/bin/env python3
"""jsonl2csv-stream —— 逐行流式地把 JSON Lines 转成 CSV(纯标准库, 常数内存)。

逐行读、逐行写, 内存中任意时刻只保留一行, 不堆积任何中间结果,
可处理上 GB 的 .jsonl 大文件。

表头(列)的确定顺序:
    1. --columns a,b,c 显式指定(最稳);
    2. 未指定且输入是普通文件: 以常数内存先扫一遍文件, 取所有顶层键的并集
       (代价是多读一遍文件);
    3. 未指定且输入是 stdin/管道: 无法回读, 报错退出。

值规则: 标量原样写出; 嵌套 dict/list → 紧凑 JSON 文本; 缺键或 null → 空单元格;
true/false 写为 true/false; --columns 之外的多余键忽略。

示例:
    python -I jsonl2csv-stream.py big.jsonl -o out.csv
    python -I jsonl2csv-stream.py big.jsonl --columns id,name,score
    cat big.jsonl | python -I jsonl2csv-stream.py --columns id,name

退出码: 0 成功; 1 输入/格式错误; 2 用法错误(argparse)。
"""

import argparse
import csv
import json
import sys


# ---------------- JSONL 迭代(逐行, 常数内存) ----------------

def _iter_jsonl(fh):
    for lineno, line in enumerate(fh, 1):
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError as exc:
            raise ValueError('第 %d 行不是合法 JSON: %s' % (lineno, exc)) from None
        if not isinstance(obj, dict):
            raise ValueError('第 %d 行是 %s 而非 JSON 对象, 无法转成 CSV 行'
                             % (lineno, type(obj).__name__))
        yield obj


def _scan_columns(fh):
    """常数内存地扫一遍文件, 收集所有顶层键的并集(保持首现顺序)。"""
    cols, seen = [], set()
    for obj in _iter_jsonl(fh):
        for k in obj:
            if k not in seen:
                seen.add(k)
                cols.append(k)
    return cols


def _cell(v):
    if v is None:
        return ''
    if v is True:
        return 'true'
    if v is False:
        return 'false'
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, separators=(',', ':'))
    return str(v)


# ---------------- 命令行 ----------------

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


def _open_output(path):
    if path in (None, '-'):
        return sys.stdout, False
    return open(path, 'w', encoding='utf-8', newline=''), True


def main(argv=None):
    _reconfigure_streams()
    parser = argparse.ArgumentParser(
        prog='jsonl2csv-stream',
        description='逐行流式地把 JSON Lines 转成 CSV(纯标准库, 常数内存)。')
    parser.add_argument('input', nargs='?', metavar='JSONL_FILE',
                        help="输入 .jsonl 文件; 缺省或 '-' 表示 stdin")
    parser.add_argument('--columns', metavar='a,b,c',
                        help='逗号分隔的列名(顶层键); 缺省时对文件做一遍预扫描')
    parser.add_argument('--no-header', action='store_true',
                        help='不输出表头行')
    parser.add_argument('-d', '--delimiter', default=',', metavar='CH',
                        help='CSV 字段分隔符, 默认逗号')
    parser.add_argument('-o', '--output', metavar='FILE',
                        help='输出 CSV 文件; 缺省 stdout')
    args = parser.parse_args(argv)
    if len(args.delimiter) != 1:
        raise ValueError('--delimiter 必须是单个字符')

    cols = None
    if args.columns is not None:
        cols = [c for c in args.columns.split(',') if c != '']
        if not cols:
            raise ValueError('--columns 不能为空')
        if len(set(cols)) != len(cols):
            raise ValueError('--columns 含重复列名')

    fh_in = None
    rows_iter = None
    if args.input in (None, '-'):
        if cols is None:
            raise ValueError('stdin/管道输入无法回读, 必须用 --columns 指定列')
        rows_iter = _iter_jsonl(sys.stdin)
    else:
        fh_in = open(args.input, 'r', encoding='utf-8-sig', newline='')
        if cols is None:
            cols = _scan_columns(fh_in)
            fh_in.seek(0)
        rows_iter = _iter_jsonl(fh_in)

    out, close_out = _open_output(args.output)
    try:
        writer = csv.writer(out, delimiter=args.delimiter, lineterminator='\n')
        count = 0
        if cols:
            if not args.no_header:
                writer.writerow(cols)
            for obj in rows_iter:  # 逐行写, 不在内存中堆积行
                writer.writerow([_cell(obj.get(k)) for k in cols])
                count += 1
    finally:
        if close_out:
            out.close()
        if fh_in is not None:
            fh_in.close()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
    except (ValueError, OSError, csv.Error) as exc:
        print('error: %s' % exc, file=sys.stderr)
        sys.exit(1)
