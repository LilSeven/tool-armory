#!/usr/bin/env python3
"""csv2yaml-lite —— 把 CSV 转成 YAML 对象列表(纯标准库)。

用途:
    第一行作表头, 其后每行变成 “- 键: 值” 形式的 YAML 映射序列。
    支持类型推断(--no-infer 关闭)与 --indent 自定义缩进宽度。

类型推断: '' 或 'null'(忽略大小写)→ null; 'true'/'false'(忽略大小写)→ 布尔;
整数、小数、科学计数(如 1e3)→ 数字; 其余一律按字符串(含前导零数字 007、
'nan'、'inf' 等, 保证 YAML 读回后类型不变)。长于表头的多余单元格忽略并告警,
短于表头的行用空单元格(null)补齐。

示例:
    python -I csv2yaml-lite.py data.csv -o out.yml
    python -I csv2yaml-lite.py data.csv --indent 4
    python -I csv2yaml-lite.py data.csv --no-infer
    python -I csv2yaml-lite.py data.csv -d ";" -o out.yml
    cat data.csv | python -I csv2yaml-lite.py

退出码: 0 成功; 1 输入/格式错误; 2 用法错误(argparse)。
"""

import argparse
import csv
import json
import re
import sys

# ---------------- 类型推断 ----------------

_INT_RE = re.compile(r'[+-]?(?:0|[1-9][0-9]*)\Z')
_FLOAT_RE = re.compile(
    r'[+-]?(?:(?:0|[1-9][0-9]*)(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')
_NUM_RE = re.compile(
    r'[+-]?(?:[0-9][0-9]*\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')


def _infer(text):
    if text == '':
        return None
    low = text.lower()
    if low == 'null':
        return None
    if low == 'true':
        return True
    if low == 'false':
        return False
    if _INT_RE.match(text):
        return int(text)
    if _FLOAT_RE.match(text):
        return float(text)
    return text


# ---------------- 迷你 YAML 输出器 ----------------

_MUST_QUOTE_LOWER = frozenset((
    'null', '~', 'true', 'false', 'yes', 'no', 'on', 'off',
    '.inf', '+.inf', '-.inf', '.nan',
))


def _yaml_plain_safe(s):
    """字符串能否以裸标量安全输出(用同一套规则读回后仍是同一字符串)。"""
    if s == '' or s != s.strip():
        return False
    if any(c in s for c in '\n\r\t'):
        return False
    if s[0] in '-?:,[]{}#&*!|>%@`"\'':
        return False
    if ': ' in s or s.endswith(':') or ' #' in s or '\t#' in s:
        return False
    if s.lower() in _MUST_QUOTE_LOWER:
        return False
    if '_' not in s and s.isascii():
        try:
            int(s)
            return False
        except ValueError:
            pass
        if _NUM_RE.match(s):
            return False
    return True


def _yaml_scalar_text(v):
    if v is None:
        return 'null'
    if v is True:
        return 'true'
    if v is False:
        return 'false'
    if isinstance(v, str):
        return v if _yaml_plain_safe(v) else json.dumps(v, ensure_ascii=False)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v != v:
            return '.nan'
        if v == float('inf'):
            return '.inf'
        if v == float('-inf'):
            return '-.inf'
        return repr(v)
    return _yaml_scalar_text(str(v))


def _emit_map(mapping, ind, width, out, head):
    col = ind + len(head)
    first = True
    for k, val in mapping.items():
        pad = (' ' * ind + head) if first else (' ' * col)
        first = False
        ks = _yaml_scalar_text(k)
        if isinstance(val, dict):
            if val:
                out.append(pad + ks + ':')
                _emit_map(val, col + width, width, out, '')
            else:
                out.append(pad + ks + ': {}')
        elif isinstance(val, list):
            if val:
                out.append(pad + ks + ':')
                _emit_seq(val, col + width, width, out, '')
            else:
                out.append(pad + ks + ': []')
        else:
            out.append(pad + ks + ': ' + _yaml_scalar_text(val))


def _emit_seq(items, ind, width, out, head):
    col = ind + len(head)
    first = True
    for item in items:
        pad = (' ' * ind + head) if first else (' ' * col)
        first = False
        if isinstance(item, dict):
            if item:
                _emit_map(item, col, width, out, '- ')
            else:
                out.append(pad + '- {}')
        elif isinstance(item, list):
            if item:
                _emit_seq(item, col, width, out, '- ')
            else:
                out.append(pad + '- []')
        else:
            out.append(pad + '- ' + _yaml_scalar_text(item))


def yaml_dump_node(value, width=2):
    """把单个值渲染成 YAML 块文本(以换行结尾)。"""
    out = []
    if isinstance(value, dict):
        if value:
            _emit_map(value, 0, width, out, '')
        else:
            out.append('{}')
    elif isinstance(value, list):
        if value:
            _emit_seq(value, 0, width, out, '')
        else:
            out.append('[]')
    else:
        out.append(_yaml_scalar_text(value))
    return '\n'.join(out) + '\n'


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
        prog='csv2yaml-lite',
        description='把 CSV 转成 YAML 对象列表(纯标准库)。')
    parser.add_argument('input', nargs='?', metavar='CSV_FILE',
                        help="输入 CSV 文件; 缺省或 '-' 表示 stdin")
    parser.add_argument('--indent', type=int, default=2, metavar='N',
                        help='YAML 块缩进宽度, 默认 2')
    parser.add_argument('--no-infer', action='store_true',
                        help='关闭类型推断, 所有单元格按字符串输出')
    parser.add_argument('-d', '--delimiter', default=',', metavar='CH',
                        help='CSV 字段分隔符, 默认逗号')
    parser.add_argument('-o', '--output', metavar='FILE',
                        help='输出 YAML 文件; 缺省 stdout')
    args = parser.parse_args(argv)
    if not 1 <= args.indent <= 16:
        raise ValueError('--indent 必须在 1..16 之间')
    if len(args.delimiter) != 1:
        raise ValueError('--delimiter 必须是单个字符')

    fh, close_in = _open_input(args.input)
    try:
        reader = csv.reader(fh, delimiter=args.delimiter)
        rows = [r for r in reader if r]
    finally:
        if close_in:
            fh.close()

    if not rows:
        text = '[]\n'
    else:
        header = rows[0]
        cast = (lambda s: s) if args.no_infer else _infer
        items = []
        ragged = 0
        for r in rows[1:]:
            if len(r) > len(header):
                ragged += 1
            vals = list(r[:len(header)]) + [''] * (len(header) - len(r))
            items.append({k: cast(v) for k, v in zip(header, vals)})
        if ragged:
            print('warn: %d 行的列数多于表头, 多余单元格已忽略' % ragged,
                  file=sys.stderr)
        text = yaml_dump_node(items, args.indent)

    out, close_out = _open_output(args.output)
    try:
        out.write(text)
    finally:
        if close_out:
            out.close()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
    except (ValueError, OSError, csv.Error) as exc:
        print('error: %s' % exc, file=sys.stderr)
        sys.exit(1)
