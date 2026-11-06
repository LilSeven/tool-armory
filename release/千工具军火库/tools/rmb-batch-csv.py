#!/usr/bin/env python3
"""CSV 金额列批量大写（单文件，仅 Python 标准库）。

用途：
    读取 CSV 的指定金额列，转换成人民币大写后追加为新列（或原地替换）输出：
      1234.56 → 壹仟贰佰叁拾肆元伍角陆分     1080.00 → 壹仟零捌拾元整
      0.05    → 零伍分                      -12.5   → 负壹拾贰元伍角
    单元格允许 ￥/¥/人民币 前缀、千分位逗号、结尾“元/圆”；超过 2 位小数按
    四舍五入取到分并在 stderr 提示；空白单元格输出空白；无法转换的单元格
    写入 “!!原因” 标记，工具最后以退出码 1 提示。
    编码：--enc auto 自动尝试 utf-8-sig / utf-8 / gb18030 / gbk；输出编码
    默认与识别出的输入编码一致（写文件时），写 stdout 时为 UTF-8。

用法：
    python -I rmb-batch-csv.py in.csv -o out.csv -c 金额
    python -I rmb-batch-csv.py gbk.csv -o out.csv -c 3 --enc auto -m replace

退出码：0=全部转换成功；1=存在无法转换的单元格；2=用法/读取错误。
"""

import argparse
import csv
import io
import re
import sys
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation, getcontext

getcontext().prec = 60

# ---------------------------------------------------------------- 中文数字核心
UP_DIG = '零壹贰叁肆伍陆柒捌玖'
_LEVELS = ('', '万', '亿', '万亿', '亿亿')


def fmt4(v):
    """0 < v < 10000 → 记账大写体（壹拾/壹佰壹拾/壹仟零伍）。"""
    d = UP_DIG
    th, h, t, o = v // 1000, v // 100 % 10, v // 10 % 10, v % 10
    out, need_zero = '', False
    if th:
        out += d[th] + '仟'
    if h:
        out += d[h] + '佰'
    elif th and (t or o):
        need_zero = True
    if t:
        if need_zero:
            out += '零'
        out += (d[1] if t == 1 else d[t]) + '拾'
    elif o and need_zero:
        out += '零'
    if o:
        out += d[o]
    return out


def int_to_cn(n):
    """非负整数 → 大写中文数字（<10^20），亿级以上用 万亿/亿亿 读法。"""
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
        parts.append(int_to_cn(yuan) + '元')
    if jiao:
        parts.append(UP_DIG[jiao] + '角')
    elif fen:
        parts.append('零')
    if fen:
        parts.append(UP_DIG[fen] + '分')
    if yuan and not jiao and not fen:
        parts.append('整')
    return ''.join(parts)


def parse_amount_cell(cell):
    """单元格文本 → (分, 是否四舍五入过)。"""
    t = cell.strip()
    for sym in ('人民币', 'RMB', '￥', '¥'):
        t = t.replace(sym, '')
    t = t.replace(',', '').replace('，', '').replace(' ', '').replace('\u3000', '')
    if t.endswith(('元', '圆')):
        t = t[:-1].strip()
    if not t:
        raise ValueError('空单元格')
    try:
        d = Decimal(t)
    except InvalidOperation:
        raise ValueError('不是数字：“%s”' % cell.strip())
    if not d.is_finite():
        raise ValueError('非有限数值')
    try:
        q = d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError('数值过大，无法表示到分')
    return int(q * 100), (q != d)


# ---------------------------------------------------------------- CSV 处理
def read_csv(path, enc):
    with open(path, 'rb') as f:
        raw = f.read()
    cands = ['utf-8-sig', 'utf-8', 'gb18030', 'gbk'] if enc in ('auto', '') else [enc]
    last = None
    for c in cands:
        try:
            text = raw.decode(c)
        except (UnicodeDecodeError, LookupError) as e:
            last = e
            continue
        return list(csv.reader(io.StringIO(text))), c
    raise ValueError('无法解码文件（试过 %s）：%s' % (', '.join(cands), last))


def resolve_col(header, col):
    """列名或 1 起始列号 → 0 起始下标；失败返回 None。"""
    if col.isdigit():
        i = int(col) - 1
        if 0 <= i < len(header):
            return i
        return None
    for i, h in enumerate(header):
        if h == col:
            return i
    for i, h in enumerate(header):
        if h.strip() == col.strip():
            return i
    return None


def write_out(rows, path, enc):
    if path:
        with open(path, 'w', encoding=enc, newline='') as f:
            csv.writer(f).writerows(rows)
    else:
        csv.writer(sys.stdout).writerows(rows)


def _setup_stdio():
    for st in (sys.stdout, sys.stderr, sys.stdin):
        try:
            st.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(
        prog='rmb-batch-csv.py',
        description='读取 CSV 指定金额列，追加或替换为人民币大写列后输出。')
    ap.add_argument('infile', help='输入 CSV 路径')
    ap.add_argument('-o', '--output', help='输出 CSV 路径；缺省写到 stdout')
    ap.add_argument('-c', '--col', required=True,
                    help='金额列：表头名或 1 起始列号')
    ap.add_argument('-m', '--mode', choices=('append', 'replace'), default='append',
                    help='append=追加新列（默认）；replace=原地替换该列')
    ap.add_argument('-n', '--name', help='追加列的列名（默认 “<原列名>大写”）')
    ap.add_argument('--enc', default='auto',
                    help='输入编码：auto/utf-8/gbk/gb18030…（默认 auto）')
    ap.add_argument('--out-enc', default=None,
                    help='输出编码；默认与识别出的输入编码一致（stdout 时为 utf-8）')
    args = ap.parse_args(argv)
    try:
        rows, enc = read_csv(args.infile, args.enc)
    except (OSError, ValueError) as e:
        print('读取失败：%s' % e, file=sys.stderr)
        return 2
    if not rows:
        print('CSV 为空', file=sys.stderr)
        return 2
    idx = resolve_col(rows[0], args.col)
    if idx is None:
        print('找不到金额列“%s”；表头为：%s' % (args.col, ' | '.join(rows[0])),
              file=sys.stderr)
        return 2
    out_enc = args.out_enc or (enc if args.output else 'utf-8')
    new_name = args.name or (str(rows[0][idx]).strip() + '大写')
    out = []
    if args.mode == 'append':
        out.append(list(rows[0]) + [new_name])
    else:
        out.append(list(rows[0]))
    failed = rounded = n_conv = 0
    for row in rows[1:]:
        row = list(row)
        if args.mode == 'append':
            try:
                if idx < len(row) and row[idx].strip():
                    cents, rnd = parse_amount_cell(row[idx])
                    rounded += rnd
                    row.append(cents_to_upper(cents))
                    n_conv += 1
                else:
                    row.append('')
            except ValueError as e:
                failed += 1
                row.append('!!' + str(e))
        else:
            while len(row) <= idx:
                row.append('')
            try:
                if row[idx].strip():
                    cents, rnd = parse_amount_cell(row[idx])
                    rounded += rnd
                    row[idx] = cents_to_upper(cents)
                    n_conv += 1
                else:
                    row[idx] = ''
            except ValueError as e:
                failed += 1
                row[idx] = '!!' + str(e)
        out.append(row)
    write_out(out, args.output, out_enc)
    if rounded:
        print('提示：%d 个金额超过 2 位小数，已四舍五入到分。' % rounded, file=sys.stderr)
    if failed:
        print('警告：%d 个单元格无法转换，已在输出中标记“!!”。' % failed, file=sys.stderr)
    print('已转换 %d 个金额（%s 模式，输入编码 %s）。'
          % (n_conv, '追加' if args.mode == 'append' else '替换', enc), file=sys.stderr)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
