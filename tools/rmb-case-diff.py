#!/usr/bin/env python3
"""大小写金额一致性比对（单文件，仅 Python 标准库）。

用途：
    扫描文本中成对出现的数字金额与大写金额，列出两者不一致的位置：
      * 数字金额：￥12.5 / 人民币 1,234.56元 / 88元 / 300万元 等写法；
      * 大写金额：壹仟贰佰叁拾肆元伍角陆分 等（“元/圆”结尾；“大写：”后
        也允许独立的 伍角/伍分 写法）；
      * 就近配对（间距不超过 --window 字符，默认 30），逐一比对到“分”；
      * 不一致、大写金额无法解析都会报告；一致的配对可用 -v 查看。
    大写解析兼容民间写法（拾万=壹拾万、壹佰伍=壹佰伍拾、块=元、毛=角）。

用法：
    python -I rmb-case-diff.py contract.txt
    cat contract.txt | python -I rmb-case-diff.py -w 40 -v

退出码：0=全部一致且可解析；1=发现不一致或解析失败；2=用法错误。
"""

import argparse
import re
import sys
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

# ---------------------------------------------------------------- 中文数字核心
CN_DIG = {}
for _i, _c in enumerate('零一二三四五六七八九'):
    CN_DIG[_c] = _i
CN_DIG.update({'〇': 0, '幺': 1, '两': 2})
for _i, _c in enumerate('零壹贰叁肆伍陆柒捌玖'):
    CN_DIG[_c] = _i
CN_SMALL = {'十': 10, '拾': 10, '百': 100, '佰': 100, '千': 1000, '仟': 1000}
CN_FOLK = {'廿': (20, 10), '卅': (30, 10), '卌': (40, 10), '皕': (200, 100)}


def parse_cn_int(s, folk=True):
    """中文数字串 → int。folk=False 时省略写法抛 ValueError。"""
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


# ---------------------------------------------------------------- 扫描与配对
# 数字金额：￥12.5 / 人民币 1,234.56 / 88元 / 300万元
NUM_MONEY_RE = re.compile(
    r'(?:￥|¥|人民币\s*|RMB\s*)(\d[\d,，]*(?:\.\d+)?)'
    r'|(?<![0-9.])(\d[\d,，]*(?:\.\d+)?)(?:元|圆|块)'
    r'|(?<![0-9.])(\d[\d,，]*(?:\.\d+)?)([万亿])(?:元|圆)'
)
# 大写金额：元/圆 必现；紧跟“大写”提示后也允许独立的 角/分 写法
_CN_DIG_CLS = '一二两三四五六七八九壹贰叁肆伍陆柒捌玖捨参漆'
CN_MONEY_RE = re.compile(
    r'[一二两三四五六七八九十百千万亿壹贰叁肆伍陆柒捌玖捨参漆拾佰仟]{1,20}(?:元|圆)'
    r'(?:[零]?[%s]?角)?(?:[零]?[%s]?分)?[整正]?'
    r'|(?:(?<=大写：)|(?<=大写:)|(?<=大写))[%s]{1,4}(?:角|毛)(?:[零]?[%s]?分)?[整正]?'
    % (_CN_DIG_CLS, _CN_DIG_CLS, '一二两三四五六七八九十百千万壹贰叁肆伍陆柒捌玖捨参漆拾佰仟', _CN_DIG_CLS)
)


def num_text_to_cents(raw, mult):
    d = Decimal(raw.replace(',', '').replace('，', '')) * mult * 100
    try:
        q = d.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError('数值过大，无法精确到分')
    return int(q), (q != d)


def cents_str(cents):
    sign = '-' if cents < 0 else ''
    yuan, r = divmod(abs(cents), 100)
    return '%s%d.%02d' % (sign, yuan, r)


def scan(text, window):
    """→ (pairs, leftovers, stats)"""
    events = []
    n_num = n_cn = 0
    for m in NUM_MONEY_RE.finditer(text):
        if m.group(1) is not None:
            raw, mult = m.group(1), 1
        elif m.group(2) is not None:
            raw, mult = m.group(2), 1
        else:
            raw, mult = m.group(3), (10 ** 4 if m.group(4) == '万' else 10 ** 8)
        try:
            cents, rounded = num_text_to_cents(raw, mult)
        except ValueError as e:
            cents, rounded = None, False
            err = str(e)
        else:
            err = None
        events.append({'kind': 'num', 'start': m.start(), 'end': m.end(),
                       'text': m.group(0), 'cents': cents, 'rounded': rounded,
                       'err': err})
        n_num += 1
    for m in CN_MONEY_RE.finditer(text):
        events.append({'kind': 'cn', 'start': m.start(), 'end': m.end(),
                       'text': m.group(0), 'cents': None, 'rounded': False,
                       'err': None})
        n_cn += 1
    events.sort(key=lambda e: (e['start'], -(e['end'] - e['start'])))
    merged, last_end = [], -1
    for e in events:
        if e['start'] >= last_end:
            merged.append(e)
            last_end = e['end']
    for e in merged:
        if e['kind'] == 'cn':
            try:
                e['cents'] = money_parse(e['text'], folk=True)
            except ValueError as ex:
                e['err'] = str(ex)
    pairs, stack = [], []
    for e in merged:
        if stack and e['kind'] != stack[-1]['kind'] and e['start'] - stack[-1]['end'] <= window:
            pairs.append((stack.pop(), e))
        else:
            stack.append(e)
    stats = {'num': n_num, 'cn': n_cn, 'total': len(merged)}
    return pairs, stack, stats


def line_col(text, pos):
    line = text.count('\n', 0, pos) + 1
    col = pos - text.rfind('\n', 0, pos)
    return line, col


def _decode(raw):
    for enc in ('utf-8-sig', 'utf-8', 'gb18030'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def _setup_stdio():
    for st in (sys.stdout, sys.stderr, sys.stdin):
        try:
            st.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(
        prog='rmb-case-diff.py',
        description='扫描文本中成对的数字金额与大写金额，列出不一致的位置。')
    ap.add_argument('textfile', nargs='?', help='待扫描的文本文件；留空读 stdin')
    ap.add_argument('-w', '--window', type=int, default=30,
                    help='数字与大写配对的最大间距（字符，默认 30）')
    ap.add_argument('-v', '--show-ok', action='store_true', help='同时打印一致的配对')
    args = ap.parse_args(argv)
    if args.textfile:
        try:
            with open(args.textfile, 'rb') as f:
                text = _decode(f.read())
        except OSError as e:
            print('读取失败：%s' % e, file=sys.stderr)
            return 2
    elif not sys.stdin.isatty():
        text = _decode(sys.stdin.buffer.read())
    else:
        ap.error('请提供文本文件或通过 stdin 输入')
    pairs, leftovers, stats = scan(text, args.window)
    n_bad = 0
    n_ok = 0
    for a, b in pairs:
        num = a if a['kind'] == 'num' else b
        cn = b if b['kind'] == 'cn' else a
        line, col = line_col(text, num['start'])
        if cn['err']:
            print('第%d行 第%d列: 大写金额“%s”无法解析：%s'
                  % (line, col, cn['text'], cn['err']))
            n_bad += 1
        elif num['err']:
            print('第%d行 第%d列: 数字金额“%s”无法解析：%s'
                  % (line, col, num['text'], num['err']))
            n_bad += 1
        elif num['cents'] == cn['cents']:
            n_ok += 1
            if args.show_ok:
                print('第%d行 第%d列: “%s” = “%s”（%s元）✓'
                      % (line, col, num['text'], cn['text'], cents_str(num['cents'])))
        else:
            d = abs(num['cents'] - cn['cents'])
            note = '，金额已四舍五入到分' if (num['rounded']) else ''
            print('第%d行 第%d列: 数字金额“%s”与大写金额“%s”不一致：%s元 ≠ %s元（差 %s元%s）'
                  % (line, col, num['text'], cn['text'],
                     cents_str(num['cents']), cents_str(cn['cents']), cents_str(d), note))
            n_bad += 1
    for e in leftovers:
        if e['kind'] == 'cn' and e['err']:
            line, col = line_col(text, e['start'])
            print('第%d行 第%d列: 大写金额“%s”无法解析：%s' % (line, col, e['text'], e['err']))
            n_bad += 1
    n_left = len(leftovers) - sum(1 for e in leftovers if e['kind'] == 'cn' and e['err'])
    print('共扫描 %d 处金额（数字 %d、大写 %d），配对 %d 对：一致 %d，不一致/失败 %d；未配对 %d 处。'
          % (stats['total'], stats['num'], stats['cn'], len(pairs), n_ok, n_bad, n_left))
    return 1 if n_bad else 0


if __name__ == '__main__':
    sys.exit(main())
