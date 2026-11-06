#!/usr/bin/env python3
r"""unicode-escape-tool.py —— 中文/emoji 文本与 \uXXXX、\N{...} 表示形式互相转换。

用法:
  python unicode-escape-tool.py encode [-s 文本 | 文件 | -] [-o 输出]
        [--style u|N] [--all] [--upper] [--no-pair]
  python unicode-escape-tool.py decode [-s 文本 | 文件 | -] [-o 输出] [--lenient]
  python unicode-escape-tool.py roundtrip [-s 文本 | 文件] [--style u|N]
        [--all] [--upper] [--no-pair]

示例:
  python unicode-escape-tool.py encode -s "你好，世界 Earth 🌍"
  python unicode-escape-tool.py encode -s "你好" --style N
  python unicode-escape-tool.py decode -s '\u4f60\u597d\ud83c\udf0d'
  python unicode-escape-tool.py decode -s '\N{CJK UNIFIED IDEOGRAPH-4F60}'
  python unicode-escape-tool.py decode -s '\u4f60\u597d' -o out.txt
  python unicode-escape-tool.py roundtrip -s "中文 emoji 🌍 ASCII 123"

规则:
  - encode (默认 --style u): 可打印 ASCII 原样保留; 反斜杠转义为 \\ ; \n \r \t 等
    控制字符用短转义; 其余字符输出 \uXXXX。BMP 之外(如 emoji 🌍)默认拆成代理对
    \ud83c\udf0d, --no-pair 时输出 Python 风格 \U0001F30D; --upper 输出大写
    十六进制; --all 连普通 ASCII 也转义。
  - encode --style N: 非 ASCII 字符输出 \N{Unicode 官方名称}, 查不到名称的字符
    自动回退为 \uXXXX 形式。
  - decode: 识别 \uXXXX(含代理对)、\UXXXXXXXX、\N{名称} 以及 \n \r \t \a \b \f
    \v \e \\ \" \' 等常见转义; 未知转义默认报错, --lenient 原样保留。
  - 输入/输出均为 UTF-8 文本, '-' 表示 stdin; 退出码: 0 成功, 1 错误, 2 用法错误。
"""

import argparse
import sys
import unicodedata

_HEX = '0123456789abcdefABCDEF'
_SIMPLE = {'n': '\n', 'r': '\r', 't': '\t', 'a': '\a', 'b': '\b',
           'f': '\f', 'v': '\v', 'e': '\x1b', '\\': '\\',
           '"': '"', "'": "'"}
_REV = {v: k for k, v in _SIMPLE.items()}


def _u(cp, upper):
    return ('\\u%04X' if upper else '\\u%04x') % cp


def _big_u(cp, upper):
    return ('\\U%08X' if upper else '\\U%08x') % cp


def encode_text(text, style='u', escape_all=False, upper=False, pair=True):
    """文本 -> Unicode 转义文本。"""
    if style not in ('u', 'N'):
        raise ValueError('未知 style: %r' % (style,))
    out = []
    for ch in text:
        if ch == '\\':
            out.append('\\\\')
        elif ch in _REV:
            out.append('\\' + _REV[ch])
        elif not escape_all and '\x20' <= ch <= '\x7e':
            out.append(ch)
        elif style == 'N':
            try:
                out.append('\\N{%s}' % unicodedata.name(ch))
            except ValueError:
                out.append(_u(ord(ch), upper))
        else:
            cp = ord(ch)
            if 0x10000 <= cp <= 0x10FFFF and pair:
                v = cp - 0x10000
                out.append(_u(0xD800 + (v >> 10), upper) + _u(0xDC00 + (v & 0x3FF), upper))
            elif cp > 0xFFFF:
                out.append(_big_u(cp, upper))
            else:
                out.append(_u(cp, upper))
    return ''.join(out)


def decode_text(text, lenient=False):
    """Unicode 转义文本 -> 文本; 解析失败抛 ValueError。"""
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch != '\\':
            out.append(ch)
            i += 1
            continue
        if i + 1 >= n:
            if lenient:
                out.append('\\')
                break
            raise ValueError('位置 %d: 末尾是孤立的反斜杠' % i)
        d = text[i + 1]
        if d in 'uU':
            width = 4 if d == 'u' else 8
            digits = text[i + 2:i + 2 + width]
            if len(digits) < width or any(c not in _HEX for c in digits):
                if lenient:
                    out.append(text[i:i + 2])
                    i += 2
                    continue
                raise ValueError('位置 %d: \\%s 后需要 %d 位十六进制数字' % (i, d, width))
            cp = int(digits, 16)
            if d == 'u' and 0xD800 <= cp < 0xDC00:
                seq = text[i + 6:i + 12]
                if (len(seq) == 6 and seq[:2] == '\\u'
                        and all(c in _HEX for c in seq[2:])):
                    lo = int(seq[2:], 16)
                    if 0xDC00 <= lo < 0xE000:
                        cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
                        out.append(chr(cp))
                        i += 12
                        continue
                if lenient:
                    out.append(text[i:i + 6])
                    i += 6
                    continue
                raise ValueError('位置 %d: 孤立的高代理 \\u%s' % (i, digits))
            if 0xD800 <= cp < 0xE000 or cp > 0x10FFFF:
                if lenient:
                    out.append(text[i:i + 2 + width])
                    i += 2 + width
                    continue
                raise ValueError('位置 %d: 码点无效: \\%s%s' % (i, d, digits))
            out.append(chr(cp))
            i += 2 + width
        elif d == 'N':
            end = text.find('}', i + 2)
            if end < 0:
                if lenient:
                    out.append(text[i:])
                    break
                raise ValueError('位置 %d: \\N{...} 缺少右花括号' % i)
            name = text[i + 3:end].strip()
            try:
                out.append(unicodedata.lookup(name))
            except (KeyError, ValueError):
                if lenient:
                    out.append(text[i:end + 1])
                    i = end + 1
                    continue
                raise ValueError('位置 %d: 未知 Unicode 名称: %r' % (i, name)) from None
            i = end + 1
        elif d in _SIMPLE:
            out.append(_SIMPLE[d])
            i += 2
        else:
            if lenient:
                out.append(text[i:i + 2])
                i += 2
                continue
            raise ValueError('位置 %d: 未知转义序列 \\%s' % (i, d))
    return ''.join(out)


def read_text_arg(args):
    if args.string is not None:
        return args.string
    if args.input == '-':
        return sys.stdin.read()
    with open(args.input, 'r', encoding='utf-8') as f:
        return f.read()


def write_text(text, path):
    if path:
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
    else:
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
        prog='unicode-escape-tool.py',
        description='中文/emoji 文本与 \\uXXXX、\\N{...} 表示形式互相转换。')
    sub = ap.add_subparsers(dest='cmd', metavar='{encode,decode,roundtrip}')
    sub.required = True

    p = sub.add_parser('encode', help='文本 -> \\uXXXX / \\N{...}')
    p.add_argument('input', nargs='?', default='-',
                   help="输入 UTF-8 文本文件, '-' 为 stdin (缺省 '-')")
    p.add_argument('-s', '--string', help='输入文本, 优先于文件')
    p.add_argument('-o', '--output', help='输出文本文件 (缺省打印到 stdout)')
    p.add_argument('--style', choices=('u', 'N'), default='u',
                   help='u=\\uXXXX(默认), N=\\N{官方名称}')
    p.add_argument('--all', action='store_true', help='ASCII 字符也转义')
    p.add_argument('--upper', action='store_true', help='十六进制用大写')
    p.add_argument('--no-pair', action='store_true',
                   help='BMP 外字符用 \\UXXXXXXXX 而不是代理对')

    p = sub.add_parser('decode', help='\\uXXXX / \\N{...} -> 文本')
    p.add_argument('input', nargs='?', default='-',
                   help="输入转义文本文件, '-' 为 stdin (缺省 '-')")
    p.add_argument('-s', '--string', help='输入转义文本, 优先于文件')
    p.add_argument('-o', '--output', help='输出文本文件 (缺省打印到 stdout)')
    p.add_argument('--lenient', action='store_true',
                   help='未知/不完整转义原样保留而不报错')

    p = sub.add_parser('roundtrip', help='encode -> decode -> 比对, 用于自检')
    p.add_argument('input', nargs='?', default='-',
                   help="输入 UTF-8 文本文件, '-' 为 stdin")
    p.add_argument('-s', '--string', help='输入文本, 优先于文件')
    p.add_argument('--style', choices=('u', 'N'), default='u', help='编码风格 (默认 u)')
    p.add_argument('--all', action='store_true', help='ASCII 字符也转义')
    p.add_argument('--upper', action='store_true', help='十六进制用大写')
    p.add_argument('--no-pair', action='store_true',
                   help='BMP 外字符用 \\UXXXXXXXX 而不是代理对')

    args = ap.parse_args(argv)
    try:
        if args.cmd == 'encode':
            text = read_text_arg(args)
            write_text(encode_text(text, args.style, args.all, args.upper,
                                   pair=not args.no_pair), args.output)
        elif args.cmd == 'decode':
            write_text(decode_text(read_text_arg(args), lenient=args.lenient),
                       args.output)
        else:
            text = read_text_arg(args)
            enc = encode_text(text, args.style, args.all, args.upper,
                              pair=not args.no_pair)
            dec = decode_text(enc)
            ok = dec == text
            print('roundtrip %s: %d 字符 (style=%s) -> %d 字符转义文本 -> %d 字符'
                  % ('OK' if ok else 'FAIL', len(text), args.style, len(enc), len(dec)))
            return 0 if ok else 1
    except (OSError, ValueError, LookupError) as exc:
        sys.stderr.write('错误: %s\n' % exc)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
