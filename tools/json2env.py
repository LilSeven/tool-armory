#!/usr/bin/env python3
"""json2env —— 把扁平 JSON 转成 KEY=VALUE 环境变量文件。

键自动大写（--keep-case 保留原大小写）；嵌套对象的键用下划线连接
（db.host -> DB_HOST）；非字符串值转 JSON 字面量（true/false/null、
数值原样）；标量数组用逗号连接，复杂数组转紧凑 JSON。值含空格、
# 或引号等字符时自动加双引号并转义 \\ " 与换行等；含 $ 的值优先用
单引号包裹（主流 dotenv 实现对单引号不展开变量）。键中的非法字符
统一替换为下划线。

示例:
  python json2env.py config.json -o .env
  cat config.json | python json2env.py
  python json2env.py config.json --sort --keep-case
"""
import argparse
import json
import re
import sys

_QUOTE_TRIGGERS = ' \t\r\n#\'"\\'


def to_scalar(value):
    """非字符串标量转 JSON 字面量文本。"""
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, str):
        return value
    return json.dumps(value)


def normalize_key(key):
    return re.sub(r'[^A-Za-z0-9_]', '_', str(key))


def flatten(value, prefix, keep_case):
    """递归拍平，返回 [(key, str_value), ...]，保持 JSON 出现顺序。"""
    pairs = []
    if isinstance(value, dict):
        for k, v in value.items():
            key = normalize_key(k)
            if not keep_case:
                key = key.upper()
            path = f'{prefix}_{key}' if prefix else key
            pairs.extend(flatten(v, path, keep_case))
    elif isinstance(value, list):
        if value and all(isinstance(x, (str, int, float, bool)) or x is None
                         for x in value):
            text = ','.join('' if x is None else to_scalar(x) for x in value)
        else:
            text = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        pairs.append((prefix, text))
    else:
        pairs.append((prefix, to_scalar(value)))
    return pairs


def dq(text):
    out = (text.replace('\\', '\\\\')
               .replace('"', '\\"')
               .replace('\n', '\\n')
               .replace('\r', '\\r')
               .replace('\t', '\\t'))
    return f'"{out}"'


def format_value(text):
    """按 dotenv 惯例决定是否加引号及如何转义。"""
    if text == '' or any(c in text for c in _QUOTE_TRIGGERS):
        return dq(text)
    if '$' in text:
        return f"'{text}'"
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='json2env', description='把 JSON 转成 KEY=VALUE 环境变量文件')
    parser.add_argument('input', nargs='?', help='JSON 文件（缺省或 - 读 stdin）')
    parser.add_argument('-o', '--output', help='输出文件（缺省写 stdout）')
    parser.add_argument('--keep-case', action='store_true',
                        help='保留键原大小写（默认全大写）')
    parser.add_argument('--sort', action='store_true', help='按键排序输出')
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', newline='')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

    try:
        if args.input and args.input != '-':
            with open(args.input, encoding='utf-8-sig', errors='replace') as f:
                text = f.read()
        else:
            try:
                sys.stdin.reconfigure(encoding='utf-8', errors='replace')
            except (AttributeError, ValueError):
                pass
            text = sys.stdin.read()
    except OSError as exc:
        print(f'json2env: 无法读取输入: {exc}', file=sys.stderr)
        return 2

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f'json2env: JSON 解析失败: {exc}', file=sys.stderr)
        return 2

    pairs = flatten(data, '', args.keep_case)
    if any(not key for key, _ in pairs):
        print('json2env: 顶层 JSON 必须是对象（数组/标量无法映射为 KEY=VALUE）',
              file=sys.stderr)
        return 2
    if args.sort:
        pairs.sort(key=lambda kv: kv[0])

    lines = [f'{key}={format_value(value)}' for key, value in pairs]
    out_text = '\n'.join(lines) + ('\n' if lines else '')
    if args.output:
        try:
            with open(args.output, 'w', encoding='utf-8', newline='') as f:
                f.write(out_text)
        except OSError as exc:
            print(f'json2env: 无法写出: {exc}', file=sys.stderr)
            return 2
    else:
        sys.stdout.write(out_text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
