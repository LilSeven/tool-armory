#!/usr/bin/env python3
"""大写金额合法性校验（单文件，仅 Python 标准库）。

用途：
    校验人民币大写金额写法是否规范，逐条报错并给出修正建议：
      * 误写字符——捨→捌、参→叁、漆→柒、简体数字→大写（一→壹）、繁体（萬→万）等；
      * 单位顺序——角/分颠倒、“元”后置、“万万/亿亿”重复；
      * “整/正”位置——只能放在末尾且紧跟“元”或“角”，“分”后不得加“整”；
      * 结构问题——数字连写（壹贰）、角/分位多字、无法识别的杂字符。
    规范基准与央行《正确填写票据和结算凭证的基本规定》示例一致：
      1234.00 → 壹仟贰佰叁拾肆元整          1409.50 → 壹仟肆佰零玖元伍角
      1234.56 → 壹仟贰佰叁拾肆元伍角陆分     325.04  → 叁佰贰拾伍元零肆分
    “圆/正/毛/块”视为合法异体写法（内部归一为 元/整/角/元）；
    民间省略写法（拾万=壹拾万、壹佰伍=壹佰伍拾）记为警告并给出规范形式。

用法：
    python -I rmb-validate.py 壹仟贰佰叁拾肆元整 壹佰贰拾捨元整
    cat amounts.txt | python -I rmb-validate.py

退出码：0=全部通过（可含警告）；1=存在错误；2=用法错误。
"""

import argparse
import re
import sys

# ---------------------------------------------------------------- 中文数字核心
CN_DIG = {}
for _i, _c in enumerate('零一二三四五六七八九'):
    CN_DIG[_c] = _i
CN_DIG.update({'〇': 0, '幺': 1, '两': 2})
for _i, _c in enumerate('零壹贰叁肆伍陆柒捌玖'):
    CN_DIG[_c] = _i
CN_SMALL = {'十': 10, '拾': 10, '百': 100, '佰': 100, '千': 1000, '仟': 1000}
CN_FOLK = {'廿': (20, 10), '卅': (30, 10), '卌': (40, 10), '皕': (200, 100)}
UP_DIG = '零壹贰叁肆伍陆柒捌玖'
LOW_DIG = '零一二三四五六七八九'
_LEVELS = ('', '万', '亿', '万亿', '亿亿')


def parse_cn_int(s, folk=True):
    """中文数字串 → int。folk=False 时省略写法抛 ValueError（消息前缀“民间省略写法”）。"""
    s = (s or '').strip()
    if not s:
        raise ValueError('空字符串')
    neg = s[0] in '负負'
    if neg:
        s = s[1:].strip()
        if not s:
            raise ValueError('负号后没有数字')
    v = _parse_nonneg(s, folk)
    return -v if neg else v


def _split_on(s, chars):
    for i, c in enumerate(s):
        if c in chars:
            return s[:i], c, s[i + 1:]
    return s, None, ''


def _pure_digit_tail(tail):
    """尾段全部为非零数字（无单位、无零）→ 可按缺单位补位解读。"""
    return bool(tail) and all(ch in CN_DIG and CN_DIG[ch] != 0 for ch in tail)


def _parse_nonneg(s, folk):
    head, c, tail = _split_on(s, '亿億')
    if c:
        if any(x in tail for x in '亿億'):
            raise ValueError('“亿”出现多次')
        hv = _parse_nonneg(head, folk) if head else 1
        return hv * 10 ** 8 + _tail_value(tail, 8, folk)
    head, c, tail = _split_on(s, '万萬')
    if c:
        if any(x in tail for x in '万萬'):
            raise ValueError('“万”出现多次')
        hv = _parse_nonneg(head, folk) if head else 1
        return hv * 10 ** 4 + _tail_value(tail, 4, folk)

    total, last_unit, buf, zero_seen = 0, 0, '', False

    def take_unit(u, ch):
        nonlocal total, last_unit, buf
        if buf:
            total += int(buf) * u
            buf = ''
        elif last_unit == 0 and total == 0:
            if not folk:
                raise ValueError('民间省略写法：首位“%s”前省略了数字' % ch)
            total += u
        elif u < last_unit:
            if not folk:
                raise ValueError('民间省略写法：“%s”前省略了数字' % ch)
            total += u
        else:
            raise ValueError('“%s”前缺少数字，单位衔接异常' % ch)
        last_unit = u

    for ch in s:
        if ch in CN_DIG:
            if buf and buf[-1] != '0' and not folk:
                raise ValueError('数字连写：“%s”后应接单位' % ch)
            if CN_DIG[ch] == 0:
                zero_seen = True
            buf += str(CN_DIG[ch])
        elif ch in CN_SMALL:
            take_unit(CN_SMALL[ch], ch)
            zero_seen = False
        elif ch in CN_FOLK:
            if buf:
                raise ValueError('“%s”前有多余数字' % ch)
            v, u = CN_FOLK[ch]
            total += v
            last_unit = u
            zero_seen = False
        else:
            raise ValueError('无法识别的字符“%s”' % ch)

    if buf:
        n = int(buf)
        if last_unit > 10 and not zero_seen:
            if not folk:
                raise ValueError('民间省略写法：末尾数字“%s”后省略了单位' % buf)
            total += n * (last_unit // 10) if len(buf) == 1 else n
        else:
            total += n
    return total


def _digits_int(tail):
    """纯汉字数字串（无单位）→ int，如“三五”→35。"""
    return int(''.join(str(CN_DIG[c]) for c in tail))


def _tail_value(tail, base_exp, folk):
    """万/亿之后的尾段；“万三”这类纯数字尾按缺单位补位（万三=13000）。"""
    if not tail:
        return 0
    if _pure_digit_tail(tail):
        if not folk:
            raise ValueError('民间省略写法：“%s”后省略了单位' % tail)
        if len(tail) <= base_exp:
            return _digits_int(tail) * 10 ** (base_exp - len(tail))
        return _digits_int(tail)
    return _parse_nonneg(tail, folk)


def fmt4(v, upper=False):
    """0 < v < 10000 → 中文；upper=True 为记账大写体（壹拾/壹佰壹拾）。"""
    d = UP_DIG if upper else LOW_DIG
    u = ('仟', '佰', '拾') if upper else ('千', '百', '十')
    th, h, t, o = v // 1000, v // 100 % 10, v // 10 % 10, v % 10
    out, need_zero = '', False
    if th:
        out += d[th] + u[0]
    if h:
        out += d[h] + u[1]
    elif th and (t or o):
        need_zero = True
    if t:
        if need_zero:
            out += '零'
        if upper or th or h:
            out += (d[1] if t == 1 else d[t]) + u[2]
        else:
            out += u[2] if t == 1 else d[t] + u[2]
    elif o and need_zero:
        out += '零'
    if o:
        out += d[o]
    return out


def int_to_cn(n, upper=False):
    """非负整数 → 中文数字（<10^20），亿级以上用 万亿/亿亿 读法。"""
    if n < 0:
        return '负' + int_to_cn(-n, upper)
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
        out.append(fmt4(v, upper) + _LEVELS[i])
        pend_zero = False
    return ''.join(out)


def cents_to_upper(cents):
    """金额（分）→ 人民币大写。规范：有角无分不写整；角为 0 分非 0 时元后写零。"""
    if cents < 0:
        return '负' + cents_to_upper(-cents)
    yuan, r = divmod(cents, 100)
    jiao, fen = divmod(r, 10)
    if cents == 0:
        return '零元整'
    parts = []
    if yuan:
        parts.append(int_to_cn(yuan, True) + '元')
    if jiao:
        parts.append(UP_DIG[jiao] + '角')
    elif fen:
        parts.append('零')
    if fen:
        parts.append(UP_DIG[fen] + '分')
    if yuan and not jiao and not fen:
        parts.append('整')
    return ''.join(parts)


def money_parse(s, folk=True):
    """中文大小写金额 → 分（int）。支持 元/圆/块、角/毛、分、整/正、￥/人民币 前缀。"""
    s = (s or '').strip().replace(' ', '').replace('\u3000', '')
    s = s.replace('块', '元').replace('毛', '角')
    m = re.match(r'^(?:人民币|￥|¥|RMB)', s)
    if m:
        s = s[m.end():]
    if not s:
        raise ValueError('空金额')
    p_j = min([i for i, c in enumerate(s) if c == '角'], default=None)
    p_f = s.find('分')
    if p_j is not None and p_f != -1 and p_j > p_f:
        raise ValueError('单位顺序错误：“角”不能出现在“分”之后')
    if s[-1] in '整正':
        if len(s) >= 2 and s[-2] == '分':
            raise ValueError('“分”之后不应再写“整/正”')
        s = s[:-1]
    if any(c in s for c in '整正'):
        raise ValueError('“整/正”只能出现在金额末尾')
    iy = min([i for i, c in enumerate(s) if c == '元'], default=None)
    if iy is not None:
        yuan_s, rest = s[:iy], s[iy + 1:]
        if any(c in yuan_s for c in '角分'):
            raise ValueError('单位顺序错误：“元”之前出现“角/分”')
    elif any(c in s for c in '角分'):
        yuan_s, rest = '', s
    else:
        yuan_s, rest = s, ''
    ij = min([i for i, c in enumerate(rest) if c == '角'], default=None)
    if ij is not None:
        jiao_s, rest2 = rest[:ij], rest[ij + 1:]
    else:
        jiao_s, rest2 = '', rest
    ip = rest2.find('分')
    if ip != -1:
        fen_s, tail = rest2[:ip], rest2[ip + 1:]
        if tail:
            raise ValueError('“分”之后有多余内容“%s”' % tail)
    elif rest2:
        raise ValueError('多余内容“%s”' % rest2)
    else:
        fen_s = ''
    yuan = parse_cn_int(yuan_s, folk) if yuan_s else 0
    jiao = parse_cn_int(jiao_s, folk) if jiao_s else 0
    fen = parse_cn_int(fen_s, folk) if fen_s else 0
    if jiao > 9 or fen > 9:
        raise ValueError('“角/分”位应为单个数字')
    return yuan * 100 + jiao * 10 + fen


# ---------------------------------------------------------------- 校验逻辑
VALID_CHARS = set('零壹贰叁肆伍陆柒捌玖拾佰仟万亿元圆角分整正')

# 常见误写/简繁/异体 → 规范大写
CHAR_MAP = {
    '捨': '捌', '参': '叁', '參': '叁', '壱': '壹', '弐': '贰', '貳': '贰',
    '陸': '陆', '漆': '柒', '萬': '万', '億': '亿', '圓': '圆', '兩': '贰',
    '一': '壹', '二': '贰', '两': '贰', '三': '叁', '四': '肆', '五': '伍',
    '六': '陆', '七': '柒', '八': '捌', '九': '玖', '十': '拾', '百': '佰',
    '千': '仟', '〇': '零', '毛': '角', '块': '元',
    '廿': '贰拾', '卅': '叁拾', '卌': '肆拾', '皕': '贰佰',
}


def analyze(raw):
    """→ (errors, warnings, value_cents|None, suggestion|None)"""
    errors, warns = [], []
    s = raw.strip()
    if not s:
        errors.append('空字符串')
        return errors, warns, None, None
    m = re.match(r'^(?:人民币|￥|¥|RMB)\s*', s)
    if m:
        s = s[m.end():]
    if not s:
        errors.append('只有前缀，没有金额')
        return errors, warns, None, None
    fixed, unknown = [], False
    for i, ch in enumerate(s):
        if ch in VALID_CHARS:
            fixed.append(ch)
        elif ch in CHAR_MAP:
            errors.append('第%d个字符“%s”不规范，应写作“%s”' % (i + 1, ch, CHAR_MAP[ch]))
            fixed.append(CHAR_MAP[ch])
        else:
            errors.append('第%d个字符“%s”不是大写金额的有效字符' % (i + 1, ch))
            unknown = True
            fixed.append('')
    value, suggestion = None, None
    if not unknown:
        t = ''.join(fixed)
        try:
            value = money_parse(t, folk=False)
        except ValueError as e:
            msg = str(e)
            if msg.startswith('民间省略写法'):
                warns.append(msg)
                try:
                    value = money_parse(t, folk=True)
                except ValueError as e2:
                    errors.append('无法解析：%s' % e2)
                    value = None
            else:
                errors.append('无法解析：%s' % msg)
        if value is not None:
            suggestion = cents_to_upper(value)

            def strip_zheng(x):
                return x[:-1] if x.endswith('整') else x

            norm = t.replace('圆', '元').replace('正', '整')
            if strip_zheng(norm) != strip_zheng(suggestion):
                warns.append('建议规范写法：%s' % suggestion)
    return errors, warns, value, suggestion


def _setup_stdio():
    for st in (sys.stdout, sys.stderr, sys.stdin):
        try:
            st.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(
        prog='rmb-validate.py',
        description='校验人民币大写金额写法，逐条报错并给出修正建议。')
    ap.add_argument('amounts', nargs='*',
                    help='待校验的大写金额；留空则从 stdin 逐行读取')
    args = ap.parse_args(argv)
    if args.amounts:
        items = args.amounts
    elif not sys.stdin.isatty():
        items = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
    else:
        ap.error('请提供至少一个待校验金额（命令行参数或 stdin）')
    n_err = n_warn = 0
    for i, raw in enumerate(items, 1):
        errors, warns, value, suggestion = analyze(raw)
        n_err += len(errors)
        n_warn += len(warns)
        if not errors and not warns:
            print('[%d] “%s” ✓ 规范' % (i, raw.strip()))
            continue
        print('[%d] “%s”' % (i, raw.strip()))
        for e in errors:
            print('    ✗ 错误：%s' % e)
        for w in warns:
            print('    △ 警告：%s' % w)
        if suggestion and (errors or warns):
            print('    → 建议：%s' % suggestion)
    print('共 %d 条：%d 个错误，%d 个警告。' % (len(items), n_err, n_warn))
    return 1 if n_err else 0


if __name__ == '__main__':
    sys.exit(main())
