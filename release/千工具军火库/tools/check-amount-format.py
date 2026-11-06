#!/usr/bin/env python3
"""票据金额栏格式化(check-amount-format)。

按银行票据/结算凭证的书写要求把金额格式化为小写栏与大写栏两行(防添改排版):
    小写栏: 首位以货币符号「¤」(或 --symbol ¥)紧贴第一位数字封头, 并可向前填充
            同符号占满栏宽, 防止在前面添改数字; 金额固定保留两位小数, 千分位分节。
    大写栏: 「人民币」紧贴大写金额不留空; 到"元"为止补「整」; 有"分"时不写"整";
            到"角"为止按《支付结算办法》可不写"整"(--jiao-zheng 可强制补写)。

用法:
    python check-amount-format.py <金额>... [--width N] [--symbol 符号] [--plain] [--jiao-zheng] [--json]

示例:
    python -I check-amount-format.py 1234.5
    python -I check-amount-format.py 1234567.89 0.05 --width 18 --symbol ¥
    python -I check-amount-format.py 88.88 --plain --json

金额要求: 正数、精确到分(最多两位小数), 逗号分节可选。
退出码: 0=全部成功; 1=存在非法金额(详见 stderr); 2=用法错误。
"""

import argparse
import json
import re
import sys
from decimal import Decimal, ROUND_HALF_UP

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


# ---------------- 票据栏格式化 ----------------
def parse_amount(text):
    """解析并校验票据金额 -> Decimal(两位小数); 非法抛 ValueError"""
    t = text.strip().replace(',', '').replace('，', '')
    if not re.fullmatch(r'\d+(?:\.\d+)?', t):
        raise ValueError('无法识别的金额写法: %r (示例: 1234.5 / 1,234.00 / 88)' % text)
    if '.' in t and len(t.split('.', 1)[1]) > 2:
        raise ValueError('小数超过两位, 票据金额必须精确到分: %s' % text)
    d = Decimal(t).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if d <= 0:
        raise ValueError('票据金额必须大于 0: %s' % text)
    if d >= Decimal('10') ** 14:
        raise ValueError('金额超出票据可填写上限(<100万亿): %s' % text)
    return d


def lower_field(d, symbol='¤', width=12, plain=False):
    """小写金额栏: 符号封头 + (可选)左填充符号防添改 + 两位小数"""
    num = '{:.2f}'.format(d) if plain else '{:,.2f}'.format(d)
    s = symbol + num
    if not plain and width > len(s):
        s = symbol * (width - len(s)) + s
    return s


def upper_field(d, jiao_zheng=False):
    """大写金额栏: 「人民币」紧贴大写, 到元为止补整; 有分不写整"""
    s = '人民币' + to_rmb_upper(d)
    if jiao_zheng and s.endswith('角'):
        s += '整'
    return s


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
        description='票据金额栏格式化: 生成防添改的小写金额栏与规范大写金额栏')
    ap.add_argument('amounts', nargs='+', help='金额, 如 1234.5 / 1,234.00 / 88')
    ap.add_argument('--width', type=int, default=12,
                    help='小写栏总宽度, 不足时左侧用货币符号填充(默认 12, 0=不填充)')
    ap.add_argument('--symbol', default='¤', help='小写栏货币符号(默认 ¤, 可用 ¥)')
    ap.add_argument('--plain', action='store_true',
                    help='小写栏不加千分位、不做填充(仅符号紧贴数字)')
    ap.add_argument('--jiao-zheng', action='store_true',
                    help='大写到"角"为止时也补"整"(默认按结算办法不写)')
    ap.add_argument('--json', action='store_true', help='以 JSON 输出')
    args = ap.parse_args(argv)
    if args.width < 0:
        print('错误: --width 不能为负数', file=sys.stderr)
        return 2

    results, errors = [], []
    for a in args.amounts:
        try:
            d = parse_amount(a)
        except ValueError as exc:
            errors.append((a, str(exc)))
            print('错误: %s' % exc, file=sys.stderr)
            continue
        lower = lower_field(d, args.symbol, args.width, args.plain)
        upper = upper_field(d, args.jiao_zheng)
        results.append({'input': a, 'value': str(d),
                        'lower_field': lower, 'upper_field': upper})
        if not args.json:
            print('金额: {:,.2f}'.format(d))
            print('  小写栏: %s' % lower)
            print('  大写栏: %s' % upper)

    if args.json:
        out = results + [{'input': a, 'error': msg} for a, msg in errors]
        print(json.dumps(out, ensure_ascii=False, indent=2))
    if errors:
        print('共 %d 个金额非法, 未处理; 合法 %d 个已输出。'
              % (len(errors), len(results)), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
