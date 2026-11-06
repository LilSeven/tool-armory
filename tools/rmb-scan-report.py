#!/usr/bin/env python3
"""目录金额扫描报告(rmb-scan-report)。

递归扫描目录下的文本文件, 汇总其中出现的所有金额(阿拉伯数字金额与中文大写金额)
及其人民币大写形式, 生成 Markdown 核对清单(或 JSON), 便于财务文档核对。

用法:
    python rmb-scan-report.py <目录> [-o 输出.md] [--ext .txt,.md] [--all] [--json]

示例:
    python -I rmb-scan-report.py ./docs
    python -I rmb-scan-report.py ./docs -o 金额核对清单.md
    python -I rmb-scan-report.py ./docs --ext .txt,.csv --json

金额识别口径(避免把普通数字误判为金额):
    带货币前缀:  ¥1234 / ￥1,234.56 / RMB 500 / 人民币3000
    带货币后缀:  1234元 / 88.5元 / 5万元 / 10块 / 12块钱
    中文大写:    壹仟贰佰叁拾肆元伍角陆分 / 拾万元整 / 伍角

退出码: 0=成功(含未发现金额); 2=用法或目录错误。
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

DEFAULT_EXTS = ('.txt', '.md', '.markdown', '.rst', '.csv', '.log',
                '.ini', '.cfg', '.tex', '.json', '.xml', '.html')
SKIP_DIRS = {'.git', '.hg', '.svn', 'node_modules', '__pycache__',
             '.venv', 'venv', '.idea', '.vscode'}
MAX_SIZE = 5 * 1024 * 1024      # 单文件超过 5MB 跳过
MAX_DETAIL_ROWS = 1000          # Markdown 明细表最多行数

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


# ---------------- 中文大写金额反解析 ----------------
_CN_NUM = {'零': 0, '〇': 0, '一': 1, '壹': 1, '二': 2, '两': 2, '俩': 2, '贰': 2, '貳': 2,
           '三': 3, '叁': 3, '参': 3, '四': 4, '肆': 4, '五': 5, '伍': 5, '六': 6, '陆': 6,
           '陸': 6, '七': 7, '柒': 7, '八': 8, '捌': 8, '九': 9, '玖': 9}
_CN_UNIT = {'十': 10, '拾': 10, '百': 100, '佰': 100, '千': 1000, '仟': 1000}
_CN_BIGU = {'万': 10 ** 4, '萬': 10 ** 4, '亿': 10 ** 8, '億': 10 ** 8}


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


RE_UPPER_PARSE = re.compile(
    r'^(?:(?P<int>[零壹贰叁参肆伍陆柒捌玖拾佰仟万亿萬億]+)元)?'
    r'(?:(?:零)?(?P<jiao>[零壹贰叁肆伍陆柒捌玖])角)?'
    r'(?:(?:零)?(?P<fen>[零壹贰叁肆伍陆柒捌玖])分)?(?:整)?$')


def parse_upper_amount(text):
    """中文大写金额 -> Decimal(2位小数); 无法完整解析返回 None"""
    m = RE_UPPER_PARSE.match(text)
    if not m or not (m.group('int') or m.group('jiao') or m.group('fen')):
        return None
    try:
        yuan = Decimal(cn_to_int(m.group('int'))) if m.group('int') else Decimal(0)
    except ValueError:
        return None
    cents = (int(_CN_NUM[m.group('jiao')]) if m.group('jiao') else 0) * 10 \
        + (int(_CN_NUM[m.group('fen')]) if m.group('fen') else 0)
    return ((yuan * 100 + cents) / 100).quantize(Decimal('0.01'))


# ---------------- 金额匹配 ----------------
_NUM = r'(?:\d{1,3}(?:,\d{3})+|\d+)'
RE_PREFIXED = re.compile(
    r'(?<![A-Za-z])(?P<pre>[¥￥]|RMB|人民币)\s?(?P<num>' + _NUM + r')(?:\.(?P<frac>\d{1,2}))?',
    re.I)
RE_SUFFIXED = re.compile(
    r'(?P<num>' + _NUM + r')(?:\.(?P<frac>\d{1,2}))?(?P<wan>万)?(?:块钱|块|元|圆)')
RE_UPPER_RUN = re.compile(r'[零壹贰叁参肆伍陆柒捌玖拾佰仟万亿萬億元角分整]{2,}')


def _q2(v):
    return v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def find_amounts(line):
    """一行文本 -> [(start, end, 原文, Decimal金额), ...]; 重叠匹配保留更早/更长的一个"""
    found = []
    for m in RE_PREFIXED.finditer(line):
        try:
            val = Decimal(m.group('num').replace(',', ''))
            if m.group('frac'):
                val += Decimal('0.' + m.group('frac'))
        except InvalidOperation:
            continue
        found.append((m.start(), m.end(), m.group(0), _q2(val)))
    for m in RE_SUFFIXED.finditer(line):
        try:
            val = Decimal(m.group('num').replace(',', ''))
            if m.group('frac'):
                val += Decimal('0.' + m.group('frac'))
            if m.group('wan'):
                val *= 10000
        except InvalidOperation:
            continue
        found.append((m.start(), m.end(), m.group(0), _q2(val)))
    for m in RE_UPPER_RUN.finditer(line):
        val = parse_upper_amount(m.group(0))
        if val is not None:
            found.append((m.start(), m.end(), m.group(0), val))
    found.sort(key=lambda t: (t[0], -t[1]))
    out, last_end = [], -1
    for item in found:
        if item[0] >= last_end:
            out.append(item)
            last_end = item[1]
    return out


def read_text(path):
    """按 UTF-8/GB18030 依次尝试解码; 都失败返回 None(视为二进制)"""
    with open(path, 'rb') as fh:
        raw = fh.read()
    for enc in ('utf-8-sig', 'utf-8', 'gb18030'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def scan_dir(root, exts, all_files):
    items, files_scanned, files_hit, skipped = [], 0, 0, 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            if not all_files and os.path.splitext(name)[1].lower() not in exts:
                continue
            files_scanned += 1
            try:
                if os.path.getsize(path) > MAX_SIZE:
                    skipped += 1
                    continue
            except OSError:
                skipped += 1
                continue
            text = read_text(path)
            if text is None:
                skipped += 1
                continue
            hit = False
            for lineno, line in enumerate(text.splitlines(), 1):
                for _s, _e, raw, val in find_amounts(line):
                    items.append({'file': os.path.relpath(path, root).replace('\\', '/'),
                                  'line': lineno, 'raw': raw, 'value': val})
                    hit = True
            if hit:
                files_hit += 1
    return items, files_scanned, files_hit, skipped


def upper_of(val):
    try:
        return to_rmb_upper(val)
    except ValueError as exc:
        return '(无法换算: %s)' % exc


def _group(items):
    groups = {}
    for it in items:
        groups.setdefault(it['value'], []).append(it)
    return sorted(groups.items(), key=lambda kv: kv[0], reverse=True)


def _total(items):
    return _q2(sum((it['value'] for it in items), Decimal(0))) if items else Decimal('0.00')


def build_markdown(root, items, files_scanned, files_hit, skipped):
    groups = _group(items)
    lines = [
        '# 金额扫描报告', '',
        '- 生成时间: %s' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        '- 扫描目录: `%s`' % os.path.abspath(root),
        '- 扫描文件: %d 个(跳过 %d 个), 含金额文件 %d 个' % (files_scanned, skipped, files_hit),
        '- 金额出现: %d 处, 去重 %d 种' % (len(items), len(groups)),
        '',
    ]
    if not items:
        lines.append('未发现金额。')
        return '\n'.join(lines)
    lines += ['## 一、金额汇总(按金额降序)', '',
              '| 序号 | 金额 | 人民币大写 | 出现次数 | 涉及文件数 |',
              '|---:|---:|---|---:|---:|']
    for i, (val, occ) in enumerate(groups, 1):
        lines.append('| %d | %s | %s | %d | %d |' % (
            i, val, upper_of(val), len(occ), len({o['file'] for o in occ})))
    lines += ['', '金额出现合计(每处计一次): **%s**' % _total(items), '']
    lines += ['## 二、明细核对清单', '',
              '| 文件 | 行 | 原文 | 数值 | 人民币大写 |',
              '|---|---:|---|---:|---|']
    for i, it in enumerate(items):
        if i >= MAX_DETAIL_ROWS:
            lines += ['', '> (其余 %d 条明细略, 可用 --json 获取全部数据)'
                      % (len(items) - MAX_DETAIL_ROWS)]
            break
        lines.append('| %s | %d | %s | %s | %s |' % (
            it['file'], it['line'], it['raw'], it['value'], upper_of(it['value'])))
    lines.append('')
    return '\n'.join(lines)


def build_json(root, items, files_scanned, files_hit, skipped):
    return {
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'root': os.path.abspath(root),
        'files_scanned': files_scanned,
        'files_skipped': skipped,
        'files_with_amounts': files_hit,
        'occurrences': len(items),
        'total': str(_total(items)),
        'summary': [{'value': str(v), 'upper': upper_of(v), 'count': len(occ),
                     'files': len({o['file'] for o in occ})} for v, occ in _group(items)],
        'items': [{'file': it['file'], 'line': it['line'], 'raw': it['raw'],
                   'value': str(it['value']), 'upper': upper_of(it['value'])}
                  for it in items],
    }


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
        description='目录金额扫描报告: 汇总文本文件中的金额及其人民币大写形式')
    ap.add_argument('directory', help='要递归扫描的目录')
    ap.add_argument('-o', '--output', help='报告输出文件(默认打印到 stdout)')
    ap.add_argument('--ext', default=','.join(DEFAULT_EXTS),
                    help='按扩展名筛选, 逗号分隔(默认常见文本扩展名)')
    ap.add_argument('--all', action='store_true', help='尝试扫描所有文件, 不限扩展名')
    ap.add_argument('--json', action='store_true', help='输出 JSON 而非 Markdown')
    args = ap.parse_args(argv)

    root = args.directory
    if not os.path.isdir(root):
        print('错误: 目录不存在: %s' % root, file=sys.stderr)
        return 2
    exts = {e.strip().lower() if e.strip().startswith('.') else '.' + e.strip().lower()
            for e in args.ext.split(',') if e.strip()}
    items, files_scanned, files_hit, skipped = scan_dir(root, exts, args.all)
    if args.json:
        out = json.dumps(build_json(root, items, files_scanned, files_hit, skipped),
                         ensure_ascii=False, indent=2)
    else:
        out = build_markdown(root, items, files_scanned, files_hit, skipped)
    if args.output:
        with open(args.output, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(out.rstrip('\n') + '\n')
        print('报告已写入: %s (金额 %d 处, 去重 %d 种)'
              % (args.output, len(items), len(_group(items))))
    else:
        print(out.rstrip('\n'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
