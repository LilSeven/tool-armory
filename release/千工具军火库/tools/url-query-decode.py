#!/usr/bin/env python3
r"""url-query-decode.py —— 拆解 URL 查询串为键值表并逐项解码, 或反向构建查询串。

用法:
  python url-query-decode.py decode [-s 文本 | 文件 | -] [-o 输出]
        [--format tsv|table|json] [--sep C] [--no-plus]
  python url-query-decode.py build [-s 文本 | 文件 | -] [-o 输出]
        [--sep C] [--no-plus] [--safe 字符]
  python url-query-decode.py roundtrip [-s 文本 | 文件] [--sep C] [--no-plus]

示例:
  python url-query-decode.py decode -s "https://example.com/search?q=%E4%BD%A0%E5%A5%BD+world&lang=zh-CN&flag"
  python url-query-decode.py decode -s "a=1&b=%E4%B8%AD%E6%96%87" --format json
  printf 'q=你好 world\nlang=zh-CN\n' | python url-query-decode.py build -
  python url-query-decode.py roundtrip -s "a=1&b=%E4%B8%AD%E6%96%87&c=x+y&flag"

规则:
  - decode: 自动截取第一个 '?' 之后、'#' 之前的部分作为查询串; 按 --sep(默认 '&')
    分项(空项跳过); 每项按第一个 '=' 拆成键值, 无 '=' 的项视为空值标志项;
    默认按表单约定把 '+' 解码为空格(--no-plus 关闭); 输出格式:
    tsv(键<TAB>值, 每项一行), table(按东亚宽度对齐的表格), json(有序数组, 无损)。
    tsv/table 中含换行等控制字符的值会破坏行结构, 需要无损时请用 json。
  - build: 输入每行 "键=值"(键值均为已解码明文, 将重新编码后拼接), 也接受
    decode --format json 的输出(自动识别); 行内含 TAB 时按第一个 TAB 拆分
    (可直接回灌 tsv 输出); 无 '=' 且无 TAB 的行视为标志项(重建时不带 '=')。
  - 文件参数为 '-' 时表示 stdin; 退出码: 0 成功, 1 数据错误, 2 用法错误。
"""

import argparse
import json
import re
import sys
import unicodedata
from urllib.parse import quote, quote_plus, unquote, unquote_plus

_MALFORMED = re.compile(r'%(?![0-9a-fA-F]{2})')


def check_safe(safe):
    for ch in safe:
        if not (0x20 <= ord(ch) < 0x7F):
            raise ValueError('--safe 只接受 ASCII 可打印字符, 收到 %r' % ch)
    return safe


def parse_pairs(text, sep='&'):
    """从 URL 或查询串中拆出 [(原始键, 原始值, 是否有等号), ...]。"""
    qpos = text.find('?')
    if qpos != -1:
        text = text[qpos + 1:]
    hpos = text.find('#')
    if hpos != -1:
        text = text[:hpos]
    pairs = []
    for part in text.split(sep):
        if not part:
            continue
        if '=' in part:
            k, v = part.split('=', 1)
            pairs.append((k, v, True))
        else:
            pairs.append((part, '', False))
    return pairs


def decode_pairs(pairs, plus=True):
    """把原始键值逐项百分号解码; 解析失败抛 ValueError。"""
    fn = unquote_plus if plus else unquote
    out = []
    for idx, (k, v, eq) in enumerate(pairs, 1):
        for label, piece in (('键', k), ('值', v)):
            m = _MALFORMED.search(piece)
            if m:
                raise ValueError('第 %d 项的%s含孤立的 %% (不是合法百分号编码): %r'
                                 % (idx, label, piece))
        try:
            out.append((fn(k, errors='strict'), fn(v, errors='strict'), eq))
        except UnicodeDecodeError as exc:
            raise ValueError('第 %d 项解码失败(%s=%s): %s' % (idx, k, v, exc)) from None
    return out


def format_tsv(rows):
    return ''.join('%s\t%s\n' % (k, v) for k, v, _ in rows)


def format_json(rows):
    return json.dumps([{'key': k, 'value': v, 'has_eq': eq} for k, v, eq in rows],
                      ensure_ascii=False, indent=2) + '\n'


def _dispw(s):
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in s)


def _pad(s, width):
    return s + ' ' * max(0, width - _dispw(s))


def format_table(rows):
    kw = max([_dispw('键')] + [_dispw(k) for k, _, _ in rows])
    vw = max([_dispw('值')] + [_dispw(v) for _, v, _ in rows])
    lines = ['%3s  %s  %s  %s' % ('#', _pad('键', kw), _pad('值', vw), '备注')]
    for i, (k, v, eq) in enumerate(rows, 1):
        lines.append('%3d  %s  %s  %s' % (i, _pad(k, kw), _pad(v, vw),
                                          '' if eq else '无等号(标志项)'))
    return '\n'.join(lines) + '\n'


def parse_build_input(text):
    """解析 build 的输入: 优先识别 JSON 数组, 否则按行解析。"""
    stripped = text.strip()
    if stripped.startswith('['):
        try:
            data = json.loads(stripped)
        except ValueError:
            data = None
        if isinstance(data, list):
            pairs = []
            for item in data:
                if isinstance(item, dict) and 'key' in item:
                    v = item.get('value')
                    pairs.append((str(item['key']),
                                  '' if v is None else str(v),
                                  bool(item.get('has_eq', True))))
                elif isinstance(item, (list, tuple)) and len(item) == 2:
                    pairs.append((str(item[0]), str(item[1]), True))
                else:
                    raise ValueError('无法识别的 JSON 项: %r' % (item,))
            return pairs
    pairs = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if '\t' in line:
            k, v = line.split('\t', 1)
            pairs.append((k, v, True))
        elif '=' in line:
            k, v = line.split('=', 1)
            pairs.append((k, v, True))
        else:
            pairs.append((line, '', False))
    return pairs


def build_query(pairs, sep='&', plus=True, safe=''):
    """把 [(键, 值, 是否有等号), ...] 重新编码为查询串。"""
    fn = quote_plus if plus else quote
    parts = []
    for k, v, eq in pairs:
        if eq:
            parts.append(fn(k, safe=safe) + '=' + fn(v, safe=safe))
        else:
            parts.append(fn(k, safe=safe))
    return sep.join(parts)


def read_text_arg(args):
    if args.string is not None:
        return args.string
    if args.input == '-':
        return sys.stdin.read()
    with open(args.input, 'r', encoding='utf-8') as f:
        return f.read()


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
        prog='url-query-decode.py',
        description='拆解 URL 查询串为键值表并逐项解码, 或反向构建查询串。')
    sub = ap.add_subparsers(dest='cmd', metavar='{decode,build,roundtrip}')
    sub.required = True

    p = sub.add_parser('decode', help='查询串 -> 键值表')
    p.add_argument('input', nargs='?', default='-',
                   help="输入 URL/查询串文件, '-' 为 stdin (缺省 '-')")
    p.add_argument('-s', '--string', help='直接给输入内容, 优先于文件')
    p.add_argument('-o', '--output', help='输出文本文件 (缺省打印到 stdout)')
    p.add_argument('--format', choices=('tsv', 'table', 'json'), default='tsv',
                   help='输出格式 (默认 tsv)')
    p.add_argument('--sep', default='&', help='参数分隔符, 单个字符 (默认 &)')
    p.add_argument('--no-plus', action='store_true', help="不把 '+' 解码为空格")

    p = sub.add_parser('build', help='键值明文 -> 查询串')
    p.add_argument('input', nargs='?', default='-',
                   help="输入文件, '-' 为 stdin (缺省 '-')")
    p.add_argument('-s', '--string', help='直接给输入内容, 优先于文件')
    p.add_argument('-o', '--output', help='输出文本文件 (缺省打印到 stdout)')
    p.add_argument('--sep', default='&', help='参数分隔符, 单个字符 (默认 &)')
    p.add_argument('--no-plus', action='store_true', help='空格用 %%20 而不是 +')
    p.add_argument('--safe', default='', help='额外保留(不编码)的 ASCII 字符集合')

    p = sub.add_parser('roundtrip', help='解码 -> 重建 -> 再解码比对, 用于自检')
    p.add_argument('input', nargs='?', default='-',
                   help="输入 URL/查询串文件, '-' 为 stdin")
    p.add_argument('-s', '--string', help='直接给输入内容, 优先于文件')
    p.add_argument('--sep', default='&', help='参数分隔符, 单个字符 (默认 &)')
    p.add_argument('--no-plus', action='store_true', help="不把 '+' 解码为空格")

    args = ap.parse_args(argv)
    try:
        if len(args.sep) != 1:
            raise ValueError('--sep 必须是单个字符, 收到 %r' % args.sep)
        safe = check_safe(getattr(args, 'safe', '') or '')
        plus = not args.no_plus
        if args.cmd == 'decode':
            rows = decode_pairs(parse_pairs(read_text_arg(args), args.sep), plus=plus)
            if args.format == 'json':
                out = format_json(rows)
            elif args.format == 'table':
                out = format_table(rows)
            else:
                out = format_tsv(rows)
            emit_text(out, args.output)
        elif args.cmd == 'build':
            pairs = parse_build_input(read_text_arg(args))
            emit_text(build_query(pairs, args.sep, plus=plus, safe=safe), args.output)
        else:
            rows1 = decode_pairs(parse_pairs(read_text_arg(args), args.sep), plus=plus)
            q = build_query(rows1, args.sep, plus=plus, safe=safe)
            rows2 = decode_pairs(parse_pairs(q, args.sep), plus=plus)
            ok = rows1 == rows2
            print('query roundtrip %s: %d 项 -> "%s"'
                  % ('OK' if ok else 'FAIL', len(rows1), q))
            return 0 if ok else 1
    except (OSError, ValueError) as exc:
        sys.stderr.write('错误: %s\n' % exc)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
