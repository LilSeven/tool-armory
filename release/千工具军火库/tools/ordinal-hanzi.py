#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""序号转中文序数（ordinal-hanzi）。

把序号转成多种中文序数风格，用于章节与条款编号：
  cn       一二三    13 -> 十三      法条/章节常用（「第十三条」）
  upper    壹贰叁    13 -> 拾叁      票据大写式
  stems    甲乙丙    13 -> 丙        天干循环（1->甲，10->癸，13->丙）
  branches 子丑寅卯  13 -> 子        地支循环（1->子，12->亥，13->子）
  ganzhi   干支      42 -> 乙巳      六十甲子按位次循环（1->甲子，38->辛丑）；
                                     注意是「第 N 位」，不是公历年份换算

用法：
    python ordinal-hanzi.py 13 [MORE ...] [--style cn|upper|stems|branches|ganzhi|all]
    python ordinal-hanzi.py 1 2 3 --style ganzhi --prefix 第 --suffix 条

输入支持 13、第13、第13条 之类写法（自动剥去「第」与「条/章/级」等后缀）。
退出码：0 = 成功；2 = 序号非法或超出范围（详情见 stderr）。

示例命令：
    python ordinal-hanzi.py 13
    # 输出：13: cn=十三 | upper=拾叁 | stems=丙 | branches=子 | ganzhi=丙子
    python ordinal-hanzi.py 38 --style ganzhi
    # 输出：辛丑
"""

import argparse
import re
import sys

STEMS = '甲乙丙丁戊己庚辛壬癸'
BRANCHES = '子丑寅卯辰巳午未申酉戌亥'
MAX_N = 10 ** 16 - 1
SUFFIX_CH = '条章节款项号回卷编部批次届层册级等类'
STYLES = ('cn', 'upper', 'stems', 'branches', 'ganzhi')


def _group(x: int, d: str, u10: str, u100: str, u1000: str) -> str:
    """1..9999 一节内的中文读法（101 -> 一百零一，110 -> 一百一十）。"""
    q, r = divmod(x, 1000)
    h, t = divmod(r, 100)
    te, o = divmod(t, 10)
    s = ''
    if q:
        s += d[q] + u1000
    if h:
        s += d[h] + u100
    if te:
        if q and not h:
            s += d[0]
        s += d[te] + u10
    if o:
        if (q or h) and not te:
            s += d[0]
        s += d[o]
    return s


def int_to_hanzi(n: int, upper: bool = False) -> str:
    """整数 -> 中文数字：13 -> 十三（小写）/ 拾叁（大写），101 -> 一百零一。"""
    d = '零壹贰叁肆伍陆柒捌玖' if upper else '零一二三四五六七八九'
    u10, u100, u1000 = ('拾', '佰', '仟') if upper else ('十', '百', '千')
    big = ('', '万', '亿', '兆')
    if n < 0:
        return '负' + int_to_hanzi(-n, upper)
    if n == 0:
        return d[0]
    groups = []
    x = n
    while x:
        groups.append(x % 10000)
        x //= 10000
    out = ''
    top = len(groups) - 1
    for i in range(top, -1, -1):
        g = groups[i]
        if g == 0:
            continue
        s = _group(g, d, u10, u100, u1000)
        if i == top and g < 20 and s.startswith(d[1] + u10):
            s = u10 + s[2:]  # 一十三 -> 十三 / 壹拾叁 -> 拾叁（序数习惯）
        if out and g < 1000:
            out += d[0]
        out += s + (big[i] if i < len(big) else '')
    return out


def clean_number(text: str) -> int:
    s = text.strip()
    s = re.sub(r'^第\s*', '', s)
    s = re.sub(rf'[{SUFFIX_CH}]\s*$', '', s).strip()
    if not re.fullmatch(r'\d+', s):
        raise ValueError(f'无法识别的序号：{text.strip()!r}')
    n = int(s)
    if n > MAX_N:
        raise ValueError(f'序号超出范围（需 <10^16）：{n}')
    return n


def convert(n: int, style: str) -> str:
    if style == 'cn':
        return int_to_hanzi(n, upper=False)
    if style == 'upper':
        return int_to_hanzi(n, upper=True)
    if style == 'stems':
        return STEMS[(n - 1) % 10]
    if style == 'branches':
        return BRANCHES[(n - 1) % 12]
    if style == 'ganzhi':
        return STEMS[(n - 1) % 10] + BRANCHES[(n - 1) % 12]
    raise ValueError(f'未知风格：{style}')


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8')
            except Exception:
                pass
    ap = argparse.ArgumentParser(
        description='把序号转成多种中文序数风格（一二三/甲乙丙/子丑寅卯/干支等）')
    ap.add_argument('numbers', nargs='+', help='序号，如 13 / 第13 / 第13条')
    ap.add_argument('--style', choices=('all',) + STYLES, default='all',
                    help='输出风格，默认 all 全部列出')
    ap.add_argument('--prefix', default='', help='输出前缀，如「第」（仅 --style 非 all 时生效）')
    ap.add_argument('--suffix', default='', help='输出后缀，如「条」（仅 --style 非 all 时生效）')
    args = ap.parse_args(argv)

    failed = 0
    for item in args.numbers:
        try:
            n = clean_number(item)
        except ValueError as exc:
            print(f'ordinal-hanzi: {exc}', file=sys.stderr)
            failed += 1
            continue
        if args.style == 'all':
            print(f'{n}: ' + ' | '.join(f'{st}={convert(n, st)}' for st in STYLES))
        else:
            print(f'{args.prefix}{convert(n, args.style)}{args.suffix}')
    return 2 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
