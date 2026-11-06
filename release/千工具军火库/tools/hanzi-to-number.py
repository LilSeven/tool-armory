#!/usr/bin/env python3
"""中文数字转阿拉伯数字（单文件，仅 Python 标准库）。

用途：
    把中文数字解析为数值，兼容口语与民间写法：
      十二万三千四百五十六 → 123456      廿五 → 25   卅 → 30   卌 → 40
      两千 → 2000    二百五 → 250（缺“十”）   一百五 → 150   三千五 → 3500
      万三 → 13000   二百十三 → 213   千零五 → 1005   一二三 → 123（逐位连读）
      负三点一四 → -3.14   幺 → 1
    也顺带支持金额后缀：壹佰贰拾叁元伍角陆分 → 123.56、伍角 → 0.5、伍分 → 0.05。
    大写/小写/繁体数字字均可用（壹壹一、貳贰二、兩两 等）。

用法：
    python -I hanzi-to-number.py 廿五 两千 一百五 万三
    cat lines.txt | python -I hanzi-to-number.py

退出码：0=全部解析成功；1=存在无法解析的输入；2=用法错误。
"""

import argparse
import re
import sys
from decimal import Decimal

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


# ---------------------------------------------------------------- 主逻辑
def cn_to_num(text):
    """中文数字（可带金额后缀、小数点）→ 数值字符串。"""
    s = (text or '').strip().replace(' ', '').replace('\u3000', '')
    if not s:
        raise ValueError('空输入')
    neg = s[0] in '负負'
    if neg:
        s = s[1:]
    if any(c in s for c in '元圆角分块毛整正'):
        cents = money_parse(s, folk=True)
        out = format(Decimal(cents) / 100, 'f')
    elif '点' in s:
        left, _, right = s.partition('点')
        if not right:
            raise ValueError('“点”后没有小数位')
        fd = []
        for ch in right:
            if ch not in CN_DIG:
                raise ValueError('小数位出现非数字“%s”' % ch)
            fd.append(str(CN_DIG[ch]))
        n = parse_cn_int(left, folk=True) if left else 0
        out = '%d.%s' % (n, ''.join(fd))
    else:
        out = str(parse_cn_int(s, folk=True))
    if neg and set(out) <= {'0', '.'}:
        neg = False
    return ('-' + out) if neg else out


def _setup_stdio():
    for st in (sys.stdout, sys.stderr, sys.stdin):
        try:
            st.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(
        prog='hanzi-to-number.py',
        description='中文数字转阿拉伯数字，兼容「两」「廿」「卅」「卌」及缺单位的民间写法。')
    ap.add_argument('texts', nargs='*',
                    help='待解析的中文数字；留空则从 stdin 逐行读取')
    args = ap.parse_args(argv)
    if args.texts:
        items = args.texts
    elif not sys.stdin.isatty():
        items = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
    else:
        ap.error('请提供至少一个中文数字（命令行参数或 stdin）')
    n_bad = 0
    for x in items:
        try:
            print(cn_to_num(x))
        except ValueError as e:
            print('无法解析 “%s”：%s' % (x.strip(), e), file=sys.stderr)
            n_bad += 1
    return 1 if n_bad else 0


if __name__ == '__main__':
    sys.exit(main())
