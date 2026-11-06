#!/usr/bin/env python3
"""url-encode-tool.py —— URL 百分号编码/解码, 可用 --safe 指定额外保留字符集。

用法:
  python url-encode-tool.py encode [-s 文本 | 文件 | -] [-o 输出] [--safe 字符] [--plus]
  python url-encode-tool.py decode [-s 文本 | 文件 | -] [-o 输出] [--plus]
                                   [--encoding E] [--raw]
  python url-encode-tool.py roundtrip [-s 文本 | 文件]

示例:
  python url-encode-tool.py encode -s "hello world/中国"
  python url-encode-tool.py encode -s "a/b c" --safe "/"
  python url-encode-tool.py encode -s "q=a b" --plus
  python url-encode-tool.py decode -s "hello%20world%2F%E4%B8%AD%E5%9B%BD"
  python url-encode-tool.py decode -s "q=a+b" --plus

规则:
  - encode: 输入按 UTF-8 取字节后编码; A-Z a-z 0-9 与 _ . - ~ 永不编码;
    --safe 追加额外保留字符(仅限 ASCII); 其余字节输出 %XX; --plus 用 '+' 表示空格。
  - decode: 按 --encoding(默认 utf-8) 解码为文本; --plus 先把 '+' 变成空格;
    --raw 直接输出解码后的原始字节(适合二进制数据); 孤立的 '%' 默认报错。
  - 文件参数为 '-' 时表示 stdin; 退出码: 0 成功, 1 数据错误, 2 用法错误。
"""

import argparse
import re
import sys
from urllib.parse import quote_from_bytes, unquote, unquote_plus, unquote_to_bytes

_MALFORMED = re.compile(r'%(?![0-9a-fA-F]{2})')


def check_safe(safe):
    for ch in safe:
        if not (0x20 <= ord(ch) < 0x7F):
            raise ValueError('--safe 只接受 ASCII 可打印字符, 收到 %r' % ch)
    return safe


def encode_percent(data, safe='', plus=False):
    """bytes -> 百分号编码文本。"""
    text = quote_from_bytes(data, safe=safe)
    if plus:
        text = text.replace('%20', '+')
    return text


def validate_percent(text):
    m = _MALFORMED.search(text)
    if m:
        raise ValueError('位置 %d: 孤立的 %% 不是合法的百分号编码' % m.start())


def decode_percent(text, encoding='utf-8', plus=False, raw=False):
    """百分号编码文本 -> 文本(或 --raw 时 bytes); 解析失败抛 ValueError。"""
    validate_percent(text)
    if raw:
        return unquote_to_bytes(text)
    if plus:
        return unquote_plus(text, encoding=encoding, errors='strict')
    return unquote(text, encoding=encoding, errors='strict')


def read_bytes_arg(args):
    if args.string is not None:
        return args.string.encode('utf-8')
    if args.input == '-':
        return sys.stdin.buffer.read()
    with open(args.input, 'rb') as f:
        return f.read()


def read_text_arg(args):
    if args.string is not None:
        return args.string
    if args.input == '-':
        return sys.stdin.read()
    with open(args.input, 'r', encoding='utf-8') as f:
        return f.read()


def write_bytes(data, path):
    if path:
        with open(path, 'wb') as f:
            f.write(data)
    else:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()


def emit_text(text, path):
    if path:
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        return
    if text and not text.endswith('\n') and sys.stdout.isatty():
        text += '\n'
    sys.stdout.write(text)


def main(argv=None):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8')
            except Exception:
                pass

    ap = argparse.ArgumentParser(
        prog='url-encode-tool.py',
        description='URL 百分号编码/解码, --safe 可指定额外保留字符集。')
    sub = ap.add_subparsers(dest='cmd', metavar='{encode,decode,roundtrip}')
    sub.required = True

    p = sub.add_parser('encode', help='文本/字节 -> 百分号编码')
    p.add_argument('input', nargs='?', default='-',
                   help="输入文件(按字节读取), '-' 为 stdin (缺省 '-')")
    p.add_argument('-s', '--string', help='输入文本(按 UTF-8 取字节), 优先于文件')
    p.add_argument('-o', '--output', help='输出文本文件 (缺省打印到 stdout)')
    p.add_argument('--safe', default='', help='额外保留(不编码)的 ASCII 字符集合')
    p.add_argument('--plus', action='store_true', help="空格编码为 '+' 而不是 %%20")

    p = sub.add_parser('decode', help='百分号编码 -> 文本/字节')
    p.add_argument('input', nargs='?', default='-',
                   help="输入文本文件, '-' 为 stdin (缺省 '-')")
    p.add_argument('-s', '--string', help='输入文本, 优先于文件')
    p.add_argument('-o', '--output', help='输出文件 (缺省打印到 stdout)')
    p.add_argument('--plus', action='store_true', help="先把 '+' 解码为空格(表单风格)")
    p.add_argument('--encoding', default='utf-8', help='解码用的字符集 (默认 utf-8)')
    p.add_argument('--raw', action='store_true', help='输出原始字节而不转文本')

    p = sub.add_parser('roundtrip', help='编码 -> 解码 -> 比对, 用于自检')
    p.add_argument('input', nargs='?', default='-',
                   help="输入文件(按字节读取), '-' 为 stdin")
    p.add_argument('-s', '--string', help='输入文本(按 UTF-8 取字节), 优先于文件')
    p.add_argument('--safe', default='', help='额外保留字符集合')

    args = ap.parse_args(argv)
    try:
        safe = check_safe(getattr(args, 'safe', '') or '')
        if args.cmd == 'encode':
            data = read_bytes_arg(args)
            emit_text(encode_percent(data, safe, args.plus), args.output)
        elif args.cmd == 'decode':
            result = decode_percent(read_text_arg(args), args.encoding,
                                    args.plus, args.raw)
            if isinstance(result, bytes):
                write_bytes(result, args.output)
            else:
                emit_text(result, args.output)
        else:
            data = read_bytes_arg(args)
            enc = encode_percent(data, safe)
            back1 = unquote_to_bytes(enc)
            enc2 = encode_percent(data, safe, plus=True)
            back2 = unquote_plus(enc2, errors='strict').encode('utf-8')
            ok = back1 == data and back2 == data
            short = enc if len(enc) <= 60 else enc[:57] + '...'
            print('percent roundtrip %s: %d 字节 -> "%s"'
                  % ('OK' if ok else 'FAIL', len(data), short))
            return 0 if ok else 1
    except (OSError, ValueError) as exc:
        sys.stderr.write('错误: %s\n' % exc)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
