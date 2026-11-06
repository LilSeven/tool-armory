#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文日期解析（hanzi-date-parse）。

把「二〇二五年十一月一日」「贰零贰伍年」等中文日期解析为标准 ISO 格式：
  完整日期 -> 2025-11-01    年月 -> 2025-11    仅年份 -> 2025
简体小写（一二三）、票据大写（壹贰叁）、〇/○/零 作零、阿拉伯数字混写
（二〇二五年11月1日）均可识别；月/日支持 十/廿/卅 组合（二十一、卅一）。
日期合法性会校验（如「二月三十日」将报错）。年份按 4 位识别（含汉字逐位）。

用法：
    python hanzi-date-parse.py 二〇二五年十一月一日 [MORE ...]
    cat doc.txt | python hanzi-date-parse.py -     # 逐行读 stdin

退出码：0 = 全部解析成功；1 = 至少一个输入未识别出合法日期（详情见 stderr）。

示例命令：
    python hanzi-date-parse.py 二〇二五年十一月一日
    # 输出：二〇二五年十一月一日 -> 2025-11-01
"""

import argparse
import re
import sys
from datetime import date

DIG = {'零': 0, '〇': 0, '○': 0, '◯': 0,
       '一': 1, '壹': 1, '二': 2, '贰': 2, '两': 2, '三': 3, '叁': 3,
       '四': 4, '肆': 4, '五': 5, '伍': 5, '六': 6, '陆': 6,
       '七': 7, '柒': 7, '八': 8, '捌': 8, '九': 9, '玖': 9}
UNIT = {'十': 10, '拾': 10, '廿': 20, '卅': 30,
        '百': 100, '佰': 100, '千': 1000, '仟': 1000}

_Y = '0-9〇○◯零一二三四五六七八九壹贰叁肆伍陆柒捌玖'
_M = '0-9〇○零一二三四五六七八九十廿卅壹贰叁肆伍陆柒捌玖拾'

RE_YMD = re.compile(
    rf'(?P<y>[{_Y}]{{4}})\s*年\s*(?P<m>[{_M}]{{1,3}})\s*月\s*(?P<d>[{_M}]{{1,3}})\s*(?:日|号)')
RE_YM = re.compile(rf'(?P<y>[{_Y}]{{4}})\s*年\s*(?P<m>[{_M}]{{1,3}})\s*月')
RE_Y = re.compile(rf'(?P<y>[{_Y}]{{4}})\s*年')

FW_TRANS = str.maketrans('０１２３４５６７８９', '0123456789')


def cn_small(s: str) -> int:
    """中文数字 1..9999：十一->11, 二十一->21, 壹拾壹->11, 零一->1, 廿三->23。"""
    if s.isdigit():  # 纯阿拉伯数字（如混写「11月30日」）
        return int(s)
    total = cur = 0
    for ch in s:
        if ch in DIG:
            cur = DIG[ch]
        elif ch in UNIT:
            total += (cur or 1) * UNIT[ch]
            cur = 0
        else:
            raise ValueError(f'无法识别的字符：{ch!r}')
    return total + cur


def parse_year(s: str) -> int:
    """年份：全为单个数字汉字/阿拉伯数字时逐位拼（二〇二五->2025），
    否则按一般中文数字解析兜底（二千零二十五->2025）。"""
    if all(ch in DIG or ch.isdigit() for ch in s):
        return int(''.join(str(DIG[ch]) if ch in DIG else ch for ch in s))
    return cn_small(s)


def parse_one(text: str) -> str:
    """从一段文本中解析第一个日期，返回 ISO 片段（YYYY-MM-DD / YYYY-MM / YYYY）。"""
    text = text.translate(FW_TRANS)
    m = RE_YMD.search(text)
    if m:
        y = parse_year(m.group('y'))
        mo = cn_small(m.group('m'))
        d = cn_small(m.group('d'))
        date(y, mo, d)  # 合法性校验，非法日期抛 ValueError
        return f'{y:04d}-{mo:02d}-{d:02d}'
    m = RE_YM.search(text)
    if m:
        y = parse_year(m.group('y'))
        mo = cn_small(m.group('m'))
        if not 1 <= mo <= 12:
            raise ValueError(f'月份越界：{m.group("m")} -> {mo}')
        return f'{y:04d}-{mo:02d}'
    m = RE_Y.search(text)
    if m:
        y = parse_year(m.group('y'))
        if not 1 <= y <= 9999:
            raise ValueError(f'年份越界：{m.group("y")} -> {y}')
        return f'{y:04d}'
    raise ValueError(f'未找到日期：{text.strip()!r}')


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8')
            except Exception:
                pass
    ap = argparse.ArgumentParser(
        description='把「二〇二五年十一月一日」「贰零贰伍年」等中文日期解析为 ISO 格式')
    ap.add_argument('texts', nargs='*',
                    help='含中文日期的文本；传「-」则从 stdin 逐行读取')
    args = ap.parse_args(argv)

    inputs = list(args.texts)
    if '-' in inputs:
        inputs = [x for x in inputs if x != '-']
        inputs.extend(sys.stdin.read().splitlines())
    if not inputs:
        ap.error('至少提供一个文本，或传「-」从 stdin 读取')

    failed = 0
    for item in inputs:
        if not item.strip():
            continue
        try:
            print(f'{item.strip()} -> {parse_one(item)}')
        except ValueError as exc:
            print(f'hanzi-date-parse: {exc}', file=sys.stderr)
            failed += 1
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
