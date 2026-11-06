#!/usr/bin/env python3
"""env2json —— 把 .env 风格文件解析成 JSON 对象。

支持 KEY=VALUE、可选 export 前缀、整行 # 注释、值后以「空白+ #」开始
的行内注释；值可用单引号（字面量，不转义）或双引号（处理 \\n \\t \\r
\\" \\\\ 转义）包裹；未加引号的值原样保留为字符串（不猜测数字/布尔类型）。
空行跳过；KEY= 产出空字符串。输出 JSON 对象到 stdout 或 -o 指定文件。

示例:
  python env2json.py .env -o config.json
  python env2json.py .env --indent 0      # 紧凑输出
  cat .env | python env2json.py
"""
import argparse
import json
import re
import sys

_ESCAPES = {'n': '\n', 't': '\t', 'r': '\r', '"': '"', '\\': '\\', "'": "'"}


class EnvParseError(ValueError):
    pass


def parse_quoted(rest, lineno):
    """解析带引号的值，返回引号内文本；要求引号后只剩空白或注释。"""
    quote = rest[0]
    out = []
    i = 1
    while i < len(rest):
        ch = rest[i]
        if quote == '"' and ch == '\\' and i + 1 < len(rest):
            nxt = rest[i + 1]
            out.append(_ESCAPES.get(nxt, '\\' + nxt))
            i += 2
            continue
        if ch == quote:
            tail = rest[i + 1:].strip()
            if tail and not tail.startswith('#'):
                raise EnvParseError(
                    f'line {lineno}: 引号后有多余内容: {tail!r}')
            return ''.join(out)
        out.append(ch)
        i += 1
    raise EnvParseError(f'line {lineno}: {quote} 引号未闭合')


def parse_bare(text, _lineno):
    """未加引号的值：截掉「空白+ #」之后的行内注释。"""
    m = re.search(r'\s#', text)
    if m:
        text = text[:m.start()].rstrip()
    return text


def parse_env(text):
    data = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if re.match(r'export\s', line):
            line = line[len('export'):].lstrip()
        if '=' not in line:
            raise EnvParseError(
                f'line {lineno}: 不是 KEY=VALUE 格式: {line!r}')
        key, _, rest = line.partition('=')
        key = key.strip()
        if not key:
            raise EnvParseError(f'line {lineno}: 键为空')
        rest = rest.strip()
        if rest[:1] in ('"', "'"):
            data[key] = parse_quoted(rest, lineno)
        else:
            data[key] = parse_bare(rest, lineno)
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='env2json', description='把 .env 风格文件解析成 JSON 对象')
    parser.add_argument('input', nargs='?', help='.env 文件（缺省或 - 读 stdin）')
    parser.add_argument('-o', '--output', help='输出文件（缺省写 stdout）')
    parser.add_argument('--indent', type=int, default=2,
                        help='JSON 缩进空格数，0 表示紧凑（默认 2）')
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', newline='')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

    try:
        if args.input and args.input != '-':
            with open(args.input, encoding='utf-8-sig',
                      errors='replace') as f:
                text = f.read()
        else:
            try:
                sys.stdin.reconfigure(encoding='utf-8', errors='replace')
            except (AttributeError, ValueError):
                pass
            text = sys.stdin.read()
    except OSError as exc:
        print(f'env2json: 无法读取输入: {exc}', file=sys.stderr)
        return 2

    try:
        data = parse_env(text)
    except EnvParseError as exc:
        print(f'env2json: {exc}', file=sys.stderr)
        return 2

    out_text = json.dumps(data, ensure_ascii=False,
                          indent=(args.indent if args.indent > 0 else None))
    out_text += '\n'
    if args.output:
        try:
            with open(args.output, 'w', encoding='utf-8', newline='') as f:
                f.write(out_text)
        except OSError as exc:
            print(f'env2json: 无法写出: {exc}', file=sys.stderr)
            return 2
    else:
        sys.stdout.write(out_text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
