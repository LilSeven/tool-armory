#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文日期大写（date-hanzi-uppercase）。

把 2025-11-01 这类公历日期转成中文大写日期「贰零贰伍年壹拾壹月零壹日」，
适配票据、合同与公文落款：
  年份  逐位大写：2025 -> 贰零贰伍
  月/日 票据惯例：1-9 前加「零」（零壹日），10 -> 壹拾，11 -> 壹拾壹，
        20 -> 贰拾，21 -> 贰拾壹，31 -> 叁拾壹
--no-pad 可去掉月/日的「零」前缀（壹日 而非 零壹日）。

用法：
    python date-hanzi-uppercase.py 2025-11-01 [MORE ...] [--no-pad]
    python date-hanzi-uppercase.py 2025/1/5 1999.12.31
    cat dates.txt | python date-hanzi-uppercase.py -    # 逐行读 stdin

支持输入格式：2025-11-01 / 2025/1/5 / 2025.11.1 / 2025年11月1日 / 20251101。
退出码：0 = 全部成功；1 = 存在无法解析或非法的日期（详情见 stderr）。

示例命令：
    python date-hanzi-uppercase.py 2025-11-01
    # 输出：贰零贰伍年壹拾壹月零壹日
"""

import argparse
import re
import sys
from datetime import date

UP = '零壹贰叁肆伍陆柒捌玖'

DATE_RE = re.compile(
    r'^\s*(?:(\d{4})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})\s*日?|(\d{8}))\s*$')


def up_small(n: int) -> str:
    """1..99 的中文大写（票据式）：1->壹, 10->壹拾, 11->壹拾壹, 21->贰拾壹。"""
    if not 1 <= n <= 99:
        raise ValueError(f'月/日超出 1..99：{n}')
    if n < 10:
        return UP[n]
    tens, ones = divmod(n, 10)
    s = UP[tens] + '拾'
    if ones:
        s += UP[ones]
    return s


def to_upper_date(y: int, m: int, d: int, pad: bool = True) -> str:
    date(y, m, d)  # 非法日期（如 2 月 30 日）在此抛 ValueError
    ys = ''.join(UP[int(c)] for c in f'{y:04d}')
    ms, ds = up_small(m), up_small(d)
    if pad:
        if m < 10:
            ms = '零' + ms
        if d < 10:
            ds = '零' + ds
    return f'{ys}年{ms}月{ds}日'


def convert(text: str, pad: bool = True) -> str:
    m = DATE_RE.match(text)
    if not m:
        raise ValueError(f'无法识别的日期：{text.strip()!r}')
    if m.group(4):
        y, mo, d = (int(m.group(4)[:4]), int(m.group(4)[4:6]), int(m.group(4)[6:]))
    else:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return to_upper_date(y, mo, d, pad)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8')
            except Exception:
                pass
    ap = argparse.ArgumentParser(
        description='把 2025-11-01 转为中文大写日期（贰零贰伍年壹拾壹月零壹日）')
    ap.add_argument('dates', nargs='*',
                    help='日期：2025-11-01 / 2025/1/5 / 2025.11.1 / 2025年11月1日 / 20251101；「-」表示从 stdin 逐行读')
    ap.add_argument('--no-pad', action='store_true',
                    help='月/日为个位时不加「零」前缀（壹日 而非 零壹日）')
    args = ap.parse_args(argv)

    inputs = list(args.dates)
    if '-' in inputs:
        inputs = [x for x in inputs if x != '-']
        inputs.extend(sys.stdin.read().splitlines())
    if not inputs:
        ap.error('至少提供一个日期，或传「-」从 stdin 读取')

    failed = 0
    for item in inputs:
        if not item.strip():
            continue
        try:
            print(convert(item, pad=not args.no_pad))
        except (ValueError, OverflowError) as exc:
            print(f'date-hanzi-uppercase: {exc}', file=sys.stderr)
            failed += 1
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
