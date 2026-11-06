#!/usr/bin/env python3
"""Markdown 金额改写(rmb-markdown-rewrite)。

把 Markdown 文档中的金额就地改写为「数字（大写）」双写形式, 便于金额核对, 例如:

    ¥3,500.00  ->  ¥3,500.00（叁仟伍佰元整）
    3500元     ->  3500元（叁仟伍佰元整）
    5万元      ->  5万元（伍万元整）

自动跳过围栏代码块、行内代码、链接与图片, 不破坏 Markdown 语法;
已经带有「（大写）」的金额不会重复改写(可重复执行, 结果幂等)。

用法:
    python rmb-markdown-rewrite.py 输入.md [-o 输出.md] [--in-place] [--dry-run]

示例:
    python -I rmb-markdown-rewrite.py note.md -o note.改写.md
    python -I rmb-markdown-rewrite.py note.md --dry-run     # 只预览差异, 不写文件
    python -I rmb-markdown-rewrite.py note.md --in-place    # 覆盖前自动备份为 .bak

退出码: 0=成功; 2=用法或文件错误。
"""

import argparse
import re
import shutil
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# ---------------- 人民币大写换算 ----------------
_CN_DIGIT = '零壹贰叁肆伍陆柒捌玖'
_CN_SMALL = ('', '拾', '佰', '仟')
_CN_BIG = ('', '万', '亿', '万亿')


def _int_to_cn(n):
    """非负整数 -> 中文大写数字(不含量词), 1234 -> 壹仟贰佰叁拾肆"""
    if n == 0:
        return '零'
    if n >= 10 ** 16:
        raise ValueError('整数部分超出可表示范围')
    groups = []
    s = str(n)
    while s:
        groups.insert(0, s[-4:])
        s = s[:-4]
    parts = []
    need_zero = False
    for idx, g in enumerate(groups):
        big = _CN_BIG[len(groups) - 1 - idx]
        gout = ''
        seen = False
        for i, ch in enumerate(g):
            d = int(ch)
            if d == 0:
                if seen:
                    need_zero = True
            else:
                if need_zero:
                    gout += '零'
                gout += _CN_DIGIT[d] + _CN_SMALL[len(g) - 1 - i]
                need_zero = False
                seen = True
        if gout:
            parts.append(gout + big if big else gout)
        elif parts:
            need_zero = True
    return ''.join(parts)


def to_rmb_upper(value):
    """金额 -> 人民币大写: 1234.56 -> 壹仟贰佰叁拾肆元伍角陆分; 1234 -> 壹仟贰佰叁拾肆元整"""
    d = Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if d < 0:
        raise ValueError('金额不能为负数')
    if d >= Decimal('10') ** 16:
        raise ValueError('金额超出可表示范围')
    n_int, cents = divmod(int(d * 100), 100)
    jiao, fen = divmod(cents, 10)
    if n_int == 0 and cents == 0:
        return '零元整'
    out = ''
    if n_int:
        out += _int_to_cn(n_int) + '元'
    if jiao == 0 and fen == 0:
        out += '整'
    else:
        if jiao:
            out += _CN_DIGIT[jiao] + '角'
        elif fen and n_int:
            out += '零'
        if fen:
            out += _CN_DIGIT[fen] + '分'
    return out


# ---------------- 金额匹配与改写 ----------------
_NUM = r'(?:\d{1,3}(?:,\d{3})+|\d+)'
RE_AMT = re.compile(
    r'(?<![A-Za-z])(?:(?P<pre>[¥￥]|RMB|人民币)\s?(?P<pnum>' + _NUM + r')(?:\.(?P<pfrac>\d{1,2}))?'
    r'|(?P<snum>' + _NUM + r')(?:\.(?P<sfrac>\d{1,2}))?(?P<swan>万)?(?:块钱|块|元|圆))',
    re.I)
RE_ALREADY = re.compile(r'\s*（[^）]*[零壹贰叁肆伍陆柒捌玖拾佰仟万亿整角分][^）]*）')
RE_FENCE = re.compile(r'^ {0,3}(?:```|~~~)')
RE_PROTECT = [
    re.compile(r'`+[^`]*`+'),                    # 行内代码
    re.compile(r'!?\[[^\]]*\]\([^)]*\)'),        # 链接与图片
    re.compile(r'\[[^\]]*\]\[[^\]]*\]'),         # 引用式链接
    re.compile(r'<https?://[^>\s]+>'),           # 自动链接
]


def rewrite_line(body, stats):
    """改写单行文本, 返回 (新文本, 是否有改写)"""
    stash = []

    def _stash(m):
        stash.append(m.group(0))
        return '\x00%d\x00' % (len(stash) - 1)

    work = body
    for pat in RE_PROTECT:
        work = pat.sub(_stash, work)

    changed = [False]

    def _repl(m):
        whole = m.group(0)
        if RE_ALREADY.match(work[m.end():]):
            stats['skipped_already'] += 1
            return whole
        try:
            if m.group('pre'):
                val = Decimal(m.group('pnum').replace(',', ''))
                if m.group('pfrac'):
                    val += Decimal('0.' + m.group('pfrac'))
            else:
                val = Decimal(m.group('snum').replace(',', ''))
                if m.group('sfrac'):
                    val += Decimal('0.' + m.group('sfrac'))
                if m.group('swan'):
                    val *= 10000
            upper = to_rmb_upper(val)
        except (InvalidOperation, ValueError):
            return whole
        changed[0] = True
        stats['rewrites'] += 1
        return whole + '（' + upper + '）'

    work = RE_AMT.sub(_repl, work)
    work = re.sub(r'\x00(\d+)\x00', lambda m: stash[int(m.group(1))], work)
    return work, changed[0]


def rewrite_markdown(text):
    """整篇 Markdown -> (新文本, 差异列表[(行号, 旧行, 新行)], stats)"""
    stats = {'rewrites': 0, 'skipped_already': 0, 'lines_changed': 0}
    parts = text.split('\n')
    out = []
    diffs = []
    in_fence = False
    for idx, part in enumerate(parts):
        cr = part.endswith('\r')
        body = part[:-1] if cr else part
        if RE_FENCE.match(body):
            in_fence = not in_fence
            out.append(part)
            continue
        if in_fence:
            out.append(part)
            continue
        new_body, changed = rewrite_line(body, stats)
        if changed:
            stats['lines_changed'] += 1
            diffs.append((idx + 1, body, new_body))
        out.append(new_body + ('\r' if cr else ''))
    return '\n'.join(out), diffs, stats


def read_text_file(path):
    with open(path, 'rb') as fh:
        raw = fh.read()
    for enc in ('utf-8-sig', 'utf-8', 'gb18030'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def _force_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            if (stream.encoding or '').lower().replace('-', '') != 'utf8':
                stream.reconfigure(encoding='utf-8')
        except Exception:
            pass


def main(argv=None):
    _force_utf8_stdio()
    ap = argparse.ArgumentParser(
        description='把 Markdown 中的金额改写为「数字（大写）」双写形式, 跳过代码块与链接')
    ap.add_argument('input', help='输入的 Markdown 文件')
    ap.add_argument('-o', '--output', help='输出文件(默认打印到 stdout)')
    ap.add_argument('--in-place', action='store_true',
                    help='覆盖原文件(自动备份为 <原文件>.bak)')
    ap.add_argument('--dry-run', action='store_true', help='只打印差异, 不写任何文件')
    args = ap.parse_args(argv)

    text = read_text_file(args.input)
    if text is None:
        print('错误: 无法读取或解码输入文件: %s' % args.input, file=sys.stderr)
        return 2
    new_text, diffs, stats = rewrite_markdown(text)

    if args.dry_run:
        for lineno, old, new in diffs:
            print('L%d - %s' % (lineno, old))
            print('L%d + %s' % (lineno, new))
    elif args.in_place:
        shutil.copy2(args.input, args.input + '.bak')
        with open(args.input, 'w', encoding='utf-8', newline='') as fh:
            fh.write(new_text)
        print('已改写并覆盖: %s (备份: %s)' % (args.input, args.input + '.bak'))
    elif args.output:
        with open(args.output, 'w', encoding='utf-8', newline='') as fh:
            fh.write(new_text)
        print('已写入: %s' % args.output)
    else:
        sys.stdout.write(new_text)

    print('改写 %d 处; 已是双写而跳过 %d 处; 变更 %d 行'
          % (stats['rewrites'], stats['skipped_already'], stats['lines_changed']),
          file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
