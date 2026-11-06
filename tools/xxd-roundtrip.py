#!/usr/bin/env python3
"""xxd-roundtrip.py —— 生成 xxd 风格十六进制 dump，并能从 dump 文本还原原始二进制。

用法:
  python xxd-roundtrip.py dump <文件|-> [-o 输出.txt] [--cols N] [--group N] [--base N]
  python xxd-roundtrip.py restore <dump文件|-> [-o 输出.bin] [--lenient]
  python xxd-roundtrip.py roundtrip <文件>        # dump -> restore -> 比对自检

示例:
  python xxd-roundtrip.py dump data.bin
  python xxd-roundtrip.py dump data.bin -o dump.txt --cols 8
  python xxd-roundtrip.py restore dump.txt -o data2.bin
  python xxd-roundtrip.py roundtrip data.bin
  cat dump.txt | python xxd-roundtrip.py restore -

说明:
  - dump 输出 xxd 默认风格: 8 位十六进制偏移 + 冒号, 每行 --cols(默认 16) 字节,
    按 --group(默认 2) 字节分组, 十六进制区按固定宽度左对齐补空格, 行尾为 ASCII 列
    (0x20~0x7e 原样显示, 其余显示 '.'), ASCII 列与十六进制区至少隔 2 个空格。
  - restore 逐行解析: 冒号前是偏移(仅做十六进制校验), 冒号后直到"连续 2 个以上
    空白"之前视为十六进制区(ASCII 列被忽略), 各行按出现顺序拼接; 空行和以 '#'
    开头的注释行跳过。本工具与 xxd 默认输出均满足上述 2 空格间隔要求。
  - 文件参数为 '-' 时表示 stdin; 退出码: 0 成功, 1 数据错误(含 roundtrip 不一致),
    2 用法错误。
"""

import argparse
import re
import sys


def dump_lines(data, base=0, cols=16, group=2):
    """把字节串切成 xxd 风格的行列表。"""
    if cols < 1 or group < 1:
        raise ValueError('--cols 和 --group 必须为正整数')
    ngroups = (cols + group - 1) // group
    hex_width = ngroups * (group * 2) + (ngroups - 1)
    offw = 8 if base + len(data) <= 0xFFFFFFFF else 16
    lines = []
    for off in range(0, len(data), cols):
        chunk = data[off:off + cols]
        groups = [chunk[i:i + group].hex() for i in range(0, len(chunk), group)]
        hexarea = ' '.join(groups).ljust(hex_width)
        asciiarea = ''.join(chr(b) if 0x20 <= b < 0x7F else '.' for b in chunk)
        lines.append('%0*x: %s  %s' % (offw, base + off, hexarea, asciiarea))
    return lines


def dump_text(data, base=0, cols=16, group=2):
    return ''.join(line + '\n' for line in dump_lines(data, base, cols, group))


_HEX_TOKEN = re.compile(r'[0-9a-fA-F]+')


def restore_bytes(text, lenient=False):
    """把 xxd 风格文本还原为 bytes; 解析失败抛 ValueError。"""
    out = bytearray()
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if ':' not in line:
            if lenient:
                continue
            raise ValueError('第 %d 行缺少 "偏移:" 前缀: %r' % (lineno, raw))
        off, rest = line.split(':', 1)
        try:
            int(off.strip(), 16)
        except ValueError:
            if lenient:
                continue
            raise ValueError('第 %d 行偏移不是十六进制: %r' % (lineno, off)) from None
        hexpart = re.split(r'\s{2,}', rest.strip(), maxsplit=1)[0]
        if not hexpart:
            if lenient:
                continue
            raise ValueError('第 %d 行十六进制区为空' % lineno)
        for tok in hexpart.split(' '):
            if not tok:
                continue
            if len(tok) % 2 or not _HEX_TOKEN.fullmatch(tok):
                raise ValueError(
                    '第 %d 行存在无法解析的内容 %r (要求 ASCII 列与十六进制区之间至少 2 个空格)'
                    % (lineno, tok))
            out += bytes.fromhex(tok)
    return bytes(out)


def read_binary(path):
    if path == '-':
        return sys.stdin.buffer.read()
    with open(path, 'rb') as f:
        return f.read()


def read_text(path):
    if path == '-':
        return sys.stdin.read()
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def write_binary(data, path):
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
        prog='xxd-roundtrip.py',
        description='生成 xxd 风格十六进制 dump, 或从 dump 文本还原原始二进制。')
    sub = ap.add_subparsers(dest='cmd', metavar='{dump,restore,roundtrip}')
    sub.required = True

    p = sub.add_parser('dump', help='二进制 -> xxd 风格文本')
    p.add_argument('input', nargs='?', default='-',
                   help="输入二进制文件, '-' 表示 stdin (缺省 '-')")
    p.add_argument('-o', '--output', help='输出文本文件 (缺省打印到 stdout)')
    p.add_argument('--cols', type=int, default=16, help='每行字节数 (默认 16)')
    p.add_argument('--group', type=int, default=2, help='十六进制分组字节数 (默认 2)')
    p.add_argument('--base', type=lambda s: int(s, 0), default=0,
                   help='首行起始偏移 (默认 0, 支持 0x 前缀)')

    p = sub.add_parser('restore', help='xxd 风格文本 -> 二进制')
    p.add_argument('input', nargs='?', default='-',
                   help="dump 文本文件, '-' 表示 stdin (缺省 '-')")
    p.add_argument('-o', '--output', help='输出二进制文件 (缺省写到 stdout)')
    p.add_argument('--lenient', action='store_true',
                   help='宽容模式: 跳过无法解析的行而不是报错')

    p = sub.add_parser('roundtrip', help='dump -> restore -> 比对, 用于自检')
    p.add_argument('input', help='输入二进制文件')

    args = ap.parse_args(argv)
    try:
        if args.cmd == 'dump':
            data = read_binary(args.input)
            emit_text(dump_text(data, args.base, args.cols, args.group), args.output)
        elif args.cmd == 'restore':
            data = restore_bytes(read_text(args.input), lenient=args.lenient)
            write_binary(data, args.output)
        else:
            data = read_binary(args.input)
            text = dump_text(data)
            back = restore_bytes(text)
            if back != data:
                sys.stderr.write('roundtrip FAIL: %d 字节还原后不一致\n' % len(data))
                return 1
            print('roundtrip OK: %d 字节 -> %d 行 dump -> 还原一致'
                  % (len(data), text.count('\n')))
    except (OSError, ValueError) as exc:
        sys.stderr.write('错误: %s\n' % exc)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
