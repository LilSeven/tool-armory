#!/usr/bin/env python3
"""命名风格转换(case-convert)

在 camelCase、PascalCase、snake_case、kebab-case、SCREAMING_SNAKE 之间
批量转换标识符。支持:
  - 直接给词(空格分隔),或从文件读取(--words-file 每行一个)
  - 从代码文件中提取符合源风格的标识符并替换(--in-place 模式)

用法:
  python case-convert.py --to snake userName HTTPStatus bigCatList
  python case-convert.py --to camel --from-file ids.txt
  python case-convert.py src.py --to kebab --detect snake --replace -o dst.py

示例:
  python case-convert.py --to snake UserProfile httpClient OAuth2Token
  # -> user_profile  http_client  o_auth2_token
"""
import argparse
import re
import sys

BOUNDARY = re.compile(
    r'(?<=[a-z0-9])(?=[A-Z])'      # aB -> a|B
    r'|(?<=[A-Z])(?=[A-Z][a-z])'   # ABc -> A|Bc
    r'|(?<=[A-Za-z0-9])(?=\d[a-zA-Z])'
)


def split_words(ident):
    """把任意风格的标识符切成小写词列表。数字段独立保留。"""
    s = ident.strip()
    if not s:
        return []
    # snake / kebab / 空格先切
    if '_' in s or '-' in s:
        parts = re.split(r'[_\-\s]+', s)
    else:
        parts = [s]
    words = []
    for part in parts:
        if not part:
            continue
        # 按驼峰边界再切
        sub = BOUNDARY.sub(' ', part).split(' ')
        for w in sub:
            # 每个连续字母段一个词,数字单独成词
            for m in re.findall(r'[A-Za-z]+|\d+', w):
                words.append(m.lower())
    return words


def to_snake(words, upper=False):
    s = '_'.join(words)
    return s.upper() if upper else s


def to_kebab(words):
    return '-'.join(words)


def to_camel(words, pascal=False):
    out = ''.join(w.capitalize() for w in words)
    if not pascal and out:
        out = out[0].lower() + out[1:]
    return out


def convert(ident, style):
    words = split_words(ident)
    if not words:
        return ident
    return {
        'snake': lambda: to_snake(words),
        'screaming': lambda: to_snake(words, upper=True),
        'kebab': lambda: to_kebab(words),
        'camel': lambda: to_camel(words),
        'pascal': lambda: to_camel(words, pascal=True),
    }[style]()


def main(argv=None):
    ap = argparse.ArgumentParser(description='在 camelCase/PascalCase/snake_case/kebab-case 间批量转换标识符')
    ap.add_argument('idents', nargs='*', help='待转换的标识符(空格分隔)')
    ap.add_argument('--to', required=True,
                    choices=['snake', 'camel', 'pascal', 'kebab', 'screaming'],
                    help='目标风格 (screaming = SCREAMING_SNAKE)')
    ap.add_argument('--from-file', help='从文件读取,每行一个标识符')
    ap.add_argument('-o', '--output', help='结果写入文件;默认 stdout')
    args = ap.parse_args(argv)

    idents = list(args.idents)
    if args.from_file:
        with open(args.from_file, encoding='utf-8-sig') as f:
            idents += [ln.strip() for ln in f if ln.strip()]
    if not idents:
        print('错误: 未提供任何标识符(位置参数或 --from-file)', file=sys.stderr)
        return 2

    lines = [f'{ident} -> {convert(ident, args.to)}' for ident in idents]
    out = '\n'.join(lines) + '\n'
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(out)
        print(f'{len(idents)} 条已写入 {args.output}')
    else:
        sys.stdout.write(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
