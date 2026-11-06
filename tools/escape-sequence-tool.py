#!/usr/bin/env python3
r"""escape-sequence-tool.py —— \xNN、\NNN 八进制、\uXXXX 等转义序列与原始字节互转。

用法:
  python escape-sequence-tool.py encode [-s 文本 | 文件 | -] [-o 输出] [--style x|oct]
  python escape-sequence-tool.py decode [-s 文本 | 文件 | -] [-o 输出] [--lenient]
  python escape-sequence-tool.py roundtrip [-s 文本 | 文件] [--style x|oct]

示例:
  python escape-sequence-tool.py encode -s "Hi 中文!"
  python escape-sequence-tool.py decode -s 'a\x41b\101\u4f60\U0001F600'
  python escape-sequence-tool.py encode data.bin --style oct -o esc.txt
  python escape-sequence-tool.py decode esc.txt -o data2.bin
  printf 'a\tb\xff' | python escape-sequence-tool.py encode -
  python escape-sequence-tool.py roundtrip -s "mixed 文本 123"

能力:
  - encode: 原始字节 -> 转义文本。可打印 ASCII 原样保留; 反斜杠转义为 \\ ;
    \n \r \t 用短转义; 其余字节按 --style 输出: x = \xNN 小写十六进制(默认),
    oct = \NNN 固定三位八进制(后面跟数字也不会被吞)。
  - decode: 转义文本 -> 原始字节。支持 \xNN(1~2 位十六进制)、\NNN(1~3 位八进制,
    值不得超过 \377)、\uXXXX(按 UTF-8 编码, 支持代理对 \ud83d\ude00)、
    \UXXXXXXXX、以及 \n \r \t \a \b \f \v \e \\ \" \' 和 \0(即八进制)。
    未知转义默认报错, --lenient 时原样保留。
  - 非 -s 输入: encode 按原始字节读取文件/stdin, decode 按 UTF-8 文本读取;
    转义文本中未转义的字符也按 UTF-8 进入输出。
  - 文件参数为 '-' 表示 stdin; 退出码: 0 成功, 1 解析/数据错误, 2 用法错误。
"""

import argparse
import sys

_HEX = '0123456789abcdefABCDEF'
_OCT = '01234567'
_NAMED = {'n': 0x0A, 't': 0x09, 'r': 0x0D, 'a': 0x07, 'b': 0x08,
          'f': 0x0C, 'v': 0x0B, 'e': 0x1B, '\\': 0x5C, '"': 0x22, "'": 0x27}


def encode_escapes(data, style='x'):
    """bytes -> 转义文本。"""
    if style not in ('x', 'oct'):
        raise ValueError('未知 style: %r' % (style,))
    out = []
    for b in data:
        if b == 0x5C:
            out.append('\\\\')
        elif b == 0x0A:
            out.append('\\n')
        elif b == 0x0D:
            out.append('\\r')
        elif b == 0x09:
            out.append('\\t')
        elif 0x20 <= b < 0x7F:
            out.append(chr(b))
        elif style == 'oct':
            out.append('\\%03o' % b)
        else:
            out.append('\\x%02x' % b)
    return ''.join(out)


def decode_escapes(text, lenient=False):
    """转义文本 -> bytes; 解析失败抛 ValueError。"""
    out = bytearray()
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c != '\\':
            out += c.encode('utf-8')
            i += 1
            continue
        if i + 1 >= n:
            if lenient:
                out += b'\\'
                break
            raise ValueError('位置 %d: 末尾是孤立的反斜杠' % i)
        d = text[i + 1]
        if d in 'xX':
            j = i + 2
            k = j
            while k < n and k - j < 2 and text[k] in _HEX:
                k += 1
            if k == j:
                if lenient:
                    out += text[i:i + 2].encode('utf-8')
                    i += 2
                    continue
                raise ValueError('位置 %d: \\x 后没有十六进制数字' % i)
            out.append(int(text[j:k], 16))
            i = k
        elif d in _OCT:
            j = i + 1
            k = j
            while k < n and k - j < 3 and text[k] in _OCT:
                k += 1
            value = int(text[j:k], 8)
            if value > 0xFF:
                raise ValueError('位置 %d: 八进制转义 \\%s 超出字节范围(最大 \\377)'
                                 % (i, text[j:k]))
            out.append(value)
            i = k
        elif d in 'uU':
            width = 4 if d == 'u' else 8
            digits = text[i + 2:i + 2 + width]
            if len(digits) < width or any(ch not in _HEX for ch in digits):
                if lenient:
                    out += text[i:i + 2].encode('utf-8')
                    i += 2
                    continue
                raise ValueError('位置 %d: \\%s 后需要 %d 位十六进制数字' % (i, d, width))
            cp = int(digits, 16)
            if d == 'u' and 0xD800 <= cp < 0xDC00:
                seq = text[i + 6:i + 12]
                if (len(seq) == 6 and seq[:2] == '\\u'
                        and all(ch in _HEX for ch in seq[2:])):
                    lo = int(seq[2:], 16)
                    if 0xDC00 <= lo < 0xE000:
                        cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
                        out += chr(cp).encode('utf-8')
                        i += 12
                        continue
                if lenient:
                    out += text[i:i + 6].encode('utf-8')
                    i += 6
                    continue
                raise ValueError('位置 %d: 孤立的高代理 \\u%s' % (i, digits))
            if 0xD800 <= cp < 0xE000 or cp > 0x10FFFF:
                if lenient:
                    out += text[i:i + 2 + width].encode('utf-8')
                    i += 2 + width
                    continue
                raise ValueError('位置 %d: 码点无效: \\%s%s' % (i, d, digits))
            out += chr(cp).encode('utf-8')
            i += 2 + width
        elif d in _NAMED:
            out.append(_NAMED[d])
            i += 2
        else:
            if lenient:
                out += text[i:i + 2].encode('utf-8')
                i += 2
                continue
            raise ValueError('位置 %d: 未知转义序列 \\%s' % (i, d))
    return bytes(out)


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
        prog='escape-sequence-tool.py',
        description='\\xNN、八进制 \\NNN、\\uXXXX 等转义序列与原始字节互相转换。')
    sub = ap.add_subparsers(dest='cmd', metavar='{encode,decode,roundtrip}')
    sub.required = True

    p = sub.add_parser('encode', help='原始字节 -> 转义文本')
    p.add_argument('input', nargs='?', default='-',
                   help="输入二进制文件, '-' 为 stdin (缺省 '-')")
    p.add_argument('-s', '--string', help='输入文本(按 UTF-8 取字节), 优先于文件')
    p.add_argument('-o', '--output', help='输出文本文件 (缺省打印到 stdout)')
    p.add_argument('--style', choices=('x', 'oct'), default='x',
                   help='非可打印字节的转义风格: x=\\xNN, oct=三位八进制 (默认 x)')

    p = sub.add_parser('decode', help='转义文本 -> 原始字节')
    p.add_argument('input', nargs='?', default='-',
                   help="输入转义文本文件, '-' 为 stdin (缺省 '-')")
    p.add_argument('-s', '--string', help='输入转义文本, 优先于文件')
    p.add_argument('-o', '--output', help='输出二进制文件 (缺省写到 stdout)')
    p.add_argument('--lenient', action='store_true',
                   help='未知/不完整转义原样保留而不报错')

    p = sub.add_parser('roundtrip', help='encode -> decode -> 比对, 用于自检')
    p.add_argument('input', nargs='?', default='-',
                   help="输入二进制文件, '-' 为 stdin")
    p.add_argument('-s', '--string', help='输入文本(按 UTF-8 取字节), 优先于文件')
    p.add_argument('--style', choices=('x', 'oct'), default=None,
                   help='只测该风格; 缺省两种都测')

    args = ap.parse_args(argv)
    try:
        if args.cmd == 'encode':
            data = read_bytes_arg(args)
            emit_text(encode_escapes(data, args.style), args.output)
        elif args.cmd == 'decode':
            data = decode_escapes(read_text_arg(args), lenient=args.lenient)
            write_bytes(data, args.output)
        else:
            data = read_bytes_arg(args)
            styles = [args.style] if args.style else ['x', 'oct']
            failed = False
            for style in styles:
                esc = encode_escapes(data, style)
                back = decode_escapes(esc)
                ok = back == data
                failed |= not ok
                print('style=%-3s %s: %d 字节 -> %d 字符转义文本 -> %d 字节'
                      % (style, 'OK' if ok else 'FAIL', len(data), len(esc), len(back)))
            if failed:
                return 1
    except (OSError, ValueError) as exc:
        sys.stderr.write('错误: %s\n' % exc)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
