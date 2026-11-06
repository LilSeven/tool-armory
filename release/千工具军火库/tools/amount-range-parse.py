#!/usr/bin/env python3
"""金额区间表述解析(amount-range-parse)。

把中文金额区间表述解析为数值区间, 例如:
    三到五万元         -> [30000, 50000]     区间(闭)
    十万上下           -> [90000, 110000]    约数(按±10%估算)
    不低于两万         -> [20000, +∞)        下限(含)
    超过八百           -> (800, +∞)          下限(不含)
    五千以下           -> (-∞, 5000]         上限(含)
    不到三百           -> (-∞, 300)          上限(不含)
    二十万起步         -> [200000, +∞)       下限(含)
    介于三万与五万之间 -> [30000, 50000]     区间(闭)

支持中文数字(一二三/壹贰叁/两/十百千/万亿)与阿拉伯数字(可带 万/千/百 量级)。

用法:
    python amount-range-parse.py 表述... [--json]
    python amount-range-parse.py --file 表述清单.txt [--json]

示例:
    python -I amount-range-parse.py "三到五万元" "十万上下" "不低于两万"
    python -I amount-range-parse.py --json "超过八百" "3-5万"

退出码: 0=全部解析成功; 1=存在无法解析的表述; 2=用法错误。
"""

import argparse
import json
import re
import sys
from decimal import Decimal

# ---------------- 中文数字 ----------------
_CN_NUM = {'零': 0, '〇': 0, '一': 1, '壹': 1, '二': 2, '两': 2, '俩': 2, '贰': 2, '貳': 2,
           '三': 3, '叁': 3, '参': 3, '四': 4, '肆': 4, '五': 5, '伍': 5, '六': 6, '陆': 6,
           '陸': 6, '七': 7, '柒': 7, '八': 8, '捌': 8, '九': 9, '玖': 9}
_CN_UNIT = {'十': 10, '拾': 10, '百': 100, '佰': 100, '千': 1000, '仟': 1000}
_CN_BIGU = {'万': 10 ** 4, '萬': 10 ** 4, '亿': 10 ** 8, '億': 10 ** 8}
_MULTS = {'万': Decimal(10 ** 4), '千': Decimal(1000), '百': Decimal(100)}


def cn_to_int(text):
    """中文数字串 -> int: '三千零五'->3005, '拾万'->100000; 含未收录字符抛 ValueError"""
    result = section = number = 0
    for ch in text:
        if ch in _CN_NUM:
            number = _CN_NUM[ch]
        elif ch in _CN_UNIT:
            section += (number or 1) * _CN_UNIT[ch]
            number = 0
        elif ch in _CN_BIGU:
            section = (section + number) or 1
            result += section * _CN_BIGU[ch]
            section = number = 0
        else:
            raise ValueError('无法识别的中文数字字符: %r' % ch)
    return result + section + number


# ---------------- 表述归一化 ----------------
_FW_MAP = {ord(f): t for f, t in zip('０１２３４５６７８９', '0123456789')}
_FW_MAP.update({ord('．'): '.', ord('－'): '-', ord('～'): '~',
                ord('—'): '-', ord('–'): '-', ord('，'): ','})

_CN_RUN = re.compile(r'[零〇一二两俩三四五六七八九十百千万亿壹贰叁参肆伍陆柒捌玖拾佰仟萬億]+')


def normalize(expr):
    """全角转半角; 中文数字串转成 '数值' 或 '数值@量级'。

    数值 = cn_to_int(run) 已含量级; @量级 仅作区间「量级继承」标记:
    串中含 万/亿/千/百 单位时 own=最大单位量级(不再继承), 否则可继承右侧量级。
    """
    s = expr.translate(_FW_MAP).strip()

    def repl(m):
        run = m.group(0)
        if run in ('万', '千', '百', '亿', '萬', '億'):
            return run        # 单字量级(如紧跟阿拉伯数字的"5万"), 留给量级后缀处理
        try:
            val = cn_to_int(run)
        except ValueError:
            return run
        if '亿' in run or '億' in run:
            own = 10 ** 8
        elif '万' in run or '萬' in run:
            own = 10 ** 4
        elif '千' in run or '仟' in run:
            own = 1000
        elif '百' in run or '佰' in run:
            own = 100
        else:
            own = 0        # 纯数字或仅含"十", 可继承区间量级
        return '%d@%d' % (val, own) if own else str(val)

    return _CN_RUN.sub(repl, s)


# ---------------- 区间模式 ----------------
def _tok(p):
    return (r'(?P<{p}n>\d+(?:\.\d+)?)'          # 数字
            r'(?:@(?P<{p}cm>\d+))?'              # 中文量级标记
            r'(?:(?P<{p}m>万|千|百))?'            # 阿拉伯量级
            r'(?P<{p}c>元|块|圆)?').format(p=p)  # 货币字尾


RE_BETWEEN = re.compile(r'介于\s*' + _tok('a') + r'\s*(?:和|与|及|到|至)\s*'
                        + _tok('b') + r'\s*之间')
RE_RANGE = re.compile(_tok('a') + r'\s*(?:到|至|~|-)\s*' + _tok('b'))
RE_APPROX_POST = re.compile(_tok('v') + r'\s*(?:上下|左右|前后)')
RE_APPROX_PRE = re.compile(r'(?:大约|大概|约莫|差不多|约)\s*' + _tok('v'))
RE_LOWER_PRE = re.compile(
    r'(?P<kw>不低于|不小于|不少于|大于等于|至少|最少|超过|多于|大于|高于|不止|满)\s*' + _tok('v'))
RE_LOWER_POST = re.compile(_tok('v') + r'\s*(?:以上|起步|往上|有余)')
RE_UPPER_PRE = re.compile(
    r'(?P<kw>不超过|不高于|至多|最多|小于等于|低于|小于|不到|不满)\s*' + _tok('v'))
RE_UPPER_POST = re.compile(_tok('v') + r'\s*(?:以下|以内)')
RE_SINGLE = re.compile(_tok('v'))

LOWER_PRE_CLOSED = {'不低于', '不小于', '不少于', '至少', '最少', '大于等于', '满'}
LOWER_PRE_OPEN = {'超过', '多于', '大于', '高于', '不止'}
UPPER_PRE_CLOSED = {'不超过', '不高于', '至多', '最多', '小于等于'}
UPPER_PRE_OPEN = {'低于', '小于', '不到', '不满'}


def _tok_value(m, p):
    """解析一个金额 token -> (数值, 自身量级或None)。

    cm(中文串标记)只说明该串语义量级, 数值已含, 不再相乘;
    mu(阿拉伯后缀 万/千/百)才需要相乘。
    """
    val = Decimal(m.group(p + 'n'))
    own = None
    cm = m.group(p + 'cm')
    mu = m.group(p + 'm')
    if mu:
        val *= _MULTS[mu]
        own = _MULTS[mu]
    elif cm:
        own = Decimal(cm)
    return val, own


def _r(kind, matched, low, high, low_closed, high_closed, swapped=False):
    return {'kind': kind, 'matched': matched, 'low': low, 'high': high,
            'low_closed': low_closed, 'high_closed': high_closed, 'swapped': swapped}


def parse_expr(expr):
    """解析一条表述 -> (归一化串, 结果dict) 或 (归一化串, None)"""
    s = normalize(expr)
    m = RE_BETWEEN.search(s)
    if m:
        a, am = _tok_value(m, 'a')
        b, bm = _tok_value(m, 'b')
        if am is None and bm is not None:
            a *= bm          # 量级继承, 与 RE_RANGE 一致
        swapped = a > b
        if swapped:
            a, b = b, a
        return s, _r('between', m.group(0), a, b, True, True, swapped)
    m = RE_RANGE.search(s)
    if m:
        a, am = _tok_value(m, 'a')
        b, bm = _tok_value(m, 'b')
        if am is None and bm is not None:
            a *= bm          # “三到五万”: 量级继承
        swapped = a > b
        if swapped:
            a, b = b, a
        return s, _r('range', m.group(0), a, b, True, True, swapped)
    m = RE_APPROX_POST.search(s) or RE_APPROX_PRE.search(s)
    if m:
        v, _ = _tok_value(m, 'v')
        return s, _r('approx', m.group(0), v * Decimal('0.9'), v * Decimal('1.1'), True, True)
    m = RE_LOWER_PRE.search(s)
    if m:
        v, _ = _tok_value(m, 'v')
        closed = m.group('kw') in LOWER_PRE_CLOSED
        return s, _r('lower', m.group(0), v, None, closed, False)
    m = RE_LOWER_POST.search(s)
    if m:
        v, _ = _tok_value(m, 'v')
        return s, _r('lower', m.group(0), v, None, True, False)
    m = RE_UPPER_PRE.search(s)
    if m:
        v, _ = _tok_value(m, 'v')
        closed = m.group('kw') in UPPER_PRE_CLOSED
        return s, _r('upper', m.group(0), None, v, False, closed)
    m = RE_UPPER_POST.search(s)
    if m:
        v, _ = _tok_value(m, 'v')
        return s, _r('upper', m.group(0), None, v, False, True)
    m = RE_SINGLE.search(s)
    if m:
        v, own = _tok_value(m, 'v')
        if own is None and m.group('vc') is None:
            return s, None   # 纯数字且无货币/量级语义, 不视为金额
        return s, _r('single', m.group(0), v, v, True, True)
    return s, None


# ---------------- 输出 ----------------
def _fmt_num(d):
    if d is None:
        return None
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), 'f')


def fmt_interval(r):
    lo = '-∞' if r['low'] is None else _fmt_num(r['low'])
    hi = '+∞' if r['high'] is None else _fmt_num(r['high'])
    lb = '[' if r['low_closed'] else '('
    rb = ']' if r['high_closed'] else ')'
    return '%s%s, %s%s' % (lb, lo, hi, rb)


def kind_label(r):
    k = r['kind']
    if k in ('range', 'between'):
        base = '区间(闭)' if r['low_closed'] and r['high_closed'] else '区间'
        return base + (', 端点倒置已纠正' if r.get('swapped') else '')
    if k == 'approx':
        return '约数(按±10%估算)'
    if k == 'lower':
        return '下限(%s)' % ('含' if r['low_closed'] else '不含')
    if k == 'upper':
        return '上限(%s)' % ('含' if r['high_closed'] else '不含')
    return '单值'


def _jnum(d):
    if d is None:
        return None
    if d == d.to_integral_value():
        return int(d)
    return float(d)


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
        description='解析中文金额区间表述(三到五万元/十万上下/不低于两万...)为数值区间')
    ap.add_argument('exprs', nargs='*', help='金额区间表述, 如 "三到五万元"')
    ap.add_argument('--file', help='从文件读取表述(每行一条)')
    ap.add_argument('--json', action='store_true', help='以 JSON 输出')
    args = ap.parse_args(argv)

    exprs = list(args.exprs)
    if args.file:
        try:
            with open(args.file, 'rb') as fh:
                raw = fh.read()
        except OSError as exc:
            print('错误: 无法读取文件: %s (%s)' % (args.file, exc), file=sys.stderr)
            return 2
        text = None
        for enc in ('utf-8-sig', 'utf-8', 'gb18030'):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            print('错误: 文件无法解码: %s' % args.file, file=sys.stderr)
            return 2
        exprs += [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not exprs:
        ap.print_usage(sys.stderr)
        return 2

    results, fail = [], 0
    for e in exprs:
        _s, r = parse_expr(e)
        if r is None:
            fail += 1
            print('无法解析: %s' % e, file=sys.stderr)
        else:
            results.append((e, r))
    if args.json:
        print(json.dumps([{'expr': e, 'kind': r['kind'], 'matched': r['matched'],
                           'low': _jnum(r['low']), 'high': _jnum(r['high']),
                           'low_closed': r['low_closed'], 'high_closed': r['high_closed']}
                          for e, r in results], ensure_ascii=False, indent=2))
    else:
        for e, r in results:
            print('%s  =>  %s   %s' % (e, fmt_interval(r), kind_label(r)))
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
