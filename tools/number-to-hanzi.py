#!/usr/bin/env python3
"""数字转中文小写（单文件，仅 Python 标准库）。

用途：
    非金额场景的数字 → 汉字小写读法：
      123456  → 十二万三千四百五十六
      -3.14   → 负三点一四
      0.5     → 零点五
      1e-3    → 零点零零一（可直接展开时按位读出）
      6.02e23 → 六点零二乘以十的二十三次方（科学场景口语读法）
      1e25    → 十的二十五次方
    支持千分位逗号与全角数字；整数部分可读到 10^20（万亿/亿亿级）。
    小数按位逐字读出，末尾多余的 0 省略（3.10 → 三点一）。

用法：
    python -I number-to-hanzi.py 123456 -3.14 6.02e23
    cat nums.txt | python -I number-to-hanzi.py

退出码：0=全部转换成功；1=存在无法识别的输入；2=用法错误。
"""

import argparse
import re
import sys
from decimal import Decimal

LOW_DIG = '零一二三四五六七八九'
_LEVELS = ('', '万', '亿', '万亿', '亿亿')


def fmt4(v):
    """0 < v < 10000 → 中文小写（口语体：十、一百一十、一千零二十四）。"""
    d = LOW_DIG
    th, h, t, o = v // 1000, v // 100 % 10, v // 10 % 10, v % 10
    out, need_zero = '', False
    if th:
        out += d[th] + '千'
    if h:
        out += d[h] + '百'
    elif th and (t or o):
        need_zero = True
    if t:
        if need_zero:
            out += '零'
        if th or h:
            out += (d[1] if t == 1 else d[t]) + '十'
        else:
            out += '十' if t == 1 else d[t] + '十'
    elif o and need_zero:
        out += '零'
    if o:
        out += d[o]
    return out


def int_to_cn(n):
    """非负整数 → 中文小写（<10^20），亿级以上用 万亿/亿亿 读法。"""
    if n < 0:
        return '负' + int_to_cn(-n)
    if n >= 10 ** 20:
        raise ValueError('数值超出可读范围（≥10^20）')
    if n == 0:
        return '零'
    groups = []
    while n:
        groups.append(n % 10000)
        n //= 10000
    out, pend_zero = [], False
    for i in range(len(groups) - 1, -1, -1):
        v = groups[i]
        if v == 0:
            pend_zero = bool(out)
            continue
        if out and (pend_zero or v < 1000):
            out.append('零')
        out.append(fmt4(v) + _LEVELS[i])
        pend_zero = False
    return ''.join(out)


def num_to_cn(text):
    """阿拉伯数字串 → 中文小写。支持小数、负号、千分位逗号、科学计数法。"""
    s = (text or '').strip()
    s = s.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
    s = s.replace('．', '.').replace('－', '-').replace('−', '-').replace('＋', '+')
    s = s.replace(',', '').replace('，', '').replace(' ', '')
    if not s:
        raise ValueError('空输入')
    neg = s[0] == '-'
    if neg:
        s = s[1:].strip()
    m = re.fullmatch(r'(\d+)(?:\.(\d+))?[eE]([+-]?\d+)', s)
    if m:
        out = _sci_to_cn(m.group(1), m.group(2) or '', int(m.group(3)))
        return ('负' + out) if neg else out
    m = re.fullmatch(r'(\d+)(?:\.(\d*))?', s)
    if not m:
        raise ValueError('无法识别的数字“%s”' % text.strip())
    ip, fp = m.group(1), (m.group(2) or '').rstrip('0')
    if not fp and int(ip) == 0:
        return '零'
    parts = []
    if neg:
        parts.append('负')
    n = int(ip)
    if n >= 10 ** 20:
        raise ValueError('超出可读范围，请用科学计数法（如 1.5e20）')
    parts.append(int_to_cn(n))
    if fp:
        parts.append('点' + ''.join(LOW_DIG[int(c)] for c in fp))
    return ''.join(parts)


def _sci_to_cn(ip, fp, exp):
    """科学计数法：能精确展开就直接读，否则用“…乘以十的…次方”口语。"""
    d = Decimal((ip + ('.' + fp if fp else '')) + ('e%d' % exp))
    plain = format(d, 'f')
    if '.' in plain:
        a, b = plain.split('.')
        if len(a) <= 16 and len(a) + len(b) <= 42:
            return num_to_cn(plain)
    elif len(plain) <= 16:
        return int_to_cn(int(plain))
    fp2 = fp.rstrip('0')
    mant = ip.lstrip('0') or '0'
    mant_s = mant + ('.' + fp2 if fp2 else '')
    base = '' if mant_s == '1' else num_to_cn(mant_s) + '乘以'
    sign = '负' if exp < 0 else ''
    return '%s十的%s%s次方' % (base, sign, int_to_cn(abs(exp)))


def _setup_stdio():
    for st in (sys.stdout, sys.stderr, sys.stdin):
        try:
            st.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(
        prog='number-to-hanzi.py',
        description='数字转中文小写（支持小数、负数与科学计数法口语读法）。')
    ap.add_argument('numbers', nargs='*',
                    help='待转换的数字；留空则从 stdin 逐行读取')
    args = ap.parse_args(argv)
    if args.numbers:
        items = args.numbers
    elif not sys.stdin.isatty():
        items = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
    else:
        ap.error('请提供至少一个数字（命令行参数或 stdin）')
    n_bad = 0
    for x in items:
        try:
            print(num_to_cn(x))
        except ValueError as e:
            print('无法转换 “%s”：%s' % (x.strip(), e), file=sys.stderr)
            n_bad += 1
    return 1 if n_bad else 0


if __name__ == '__main__':
    sys.exit(main())
