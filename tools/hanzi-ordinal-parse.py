#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文序号反解析（hanzi-ordinal-parse）。

把「第十三条」「丙级」「辛丑」等中文序号解析回数值或序位，各风格自动识别：
  中文数字  第十三条 -> 13     第一百零一条 -> 101    壹佰零壹号 -> 101
  天干      丙级 -> 3          （甲=1 … 癸=10）
  地支      子 -> 1            （子=1 … 亥=12）
  干支      辛丑 -> 38         （六十甲子第 38 位；甲子=1，癸亥=60）
返回值为 1 起算的数值/序位；--0base 可把天干/地支/干支的序位改为 0 起算
（辛丑 -> 37）。阿拉伯数字（101）与全角数字（１０１）也能解析。
非法干支组合（如「甲丑」，不在六十甲子中）会报错。

用法：
    python hanzi-ordinal-parse.py 第十三条 丙级 辛丑 [MORE ...] [--0base]

退出码：0 = 全部解析成功；1 = 至少一个输入无法识别（详情见 stderr）。

示例命令：
    python hanzi-ordinal-parse.py 第十三条 丙级 辛丑
    # 输出：
    # 第十三条 -> 13 (中文数字)
    # 丙级 -> 3 (天干第3)
    # 辛丑 -> 38 (干支第38位)
"""

import argparse
import re
import sys

STEMS = '甲乙丙丁戊己庚辛壬癸'
BRANCHES = '子丑寅卯辰巳午未申酉戌亥'

DIG = {'零': 0, '〇': 0, '○': 0,
       '一': 1, '壹': 1, '二': 2, '贰': 2, '两': 2, '三': 3, '叁': 3,
       '四': 4, '肆': 4, '五': 5, '伍': 5, '六': 6, '陆': 6,
       '七': 7, '柒': 7, '八': 8, '捌': 8, '九': 9, '玖': 9}
UNIT = {'十': 10, '拾': 10, '廿': 20, '卅': 30,
        '百': 100, '佰': 100, '千': 1000, '仟': 1000}
BIG = {'万': 10000, '萬': 10000, '亿': 10 ** 8, '億': 10 ** 8}

SUFFIX_CH = '条章节款项号回卷编部批次届层册级等类'
FW_TRANS = str.maketrans('０１２３４５６７８９', '0123456789')


def cn_to_int(s: str) -> int:
    """中文数字 -> 整数：十三->13, 一百零一->101, 二千零二十五->2025。"""
    total = section = cur = 0
    for ch in s:
        if ch in DIG:
            cur = DIG[ch]
        elif ch in UNIT:
            section += (cur or 1) * UNIT[ch]
            cur = 0
        elif ch in BIG:
            if section == 0 and cur == 0:
                cur = 1
            section = (section + cur) * BIG[ch]
            total += section
            section = cur = 0
        elif ch in '零〇○':
            cur = 0
        else:
            raise ValueError(f'无法识别的字符：{ch!r}')
    return total + section + cur


def strip_decor(text: str) -> str:
    """剥去「第」前缀与「条/章/级」等后缀，保留序号主体。"""
    s = text.strip().translate(FW_TRANS)
    s = re.sub(r'^第\s*', '', s)
    s = re.sub(rf'[{SUFFIX_CH}]\s*$', '', s)
    return s.strip()


def ganzhi_index(stem: str, branch: str):
    """六十甲子位次（0 起算）；组合不合法时返回 None。"""
    si, bi = STEMS.index(stem), BRANCHES.index(branch)
    for k in range(60):
        if k % 10 == si and k % 12 == bi:
            return k
    return None


def parse_one(text: str):
    """返回 (数值, 说明, 是否循环序位)。"""
    core = strip_decor(text)
    if not core:
        raise ValueError(f'空序号：{text.strip()!r}')
    if core.isdigit():
        return int(core), '阿拉伯数字', False
    if len(core) == 2 and core[0] in STEMS and core[1] in BRANCHES:
        k = ganzhi_index(core[0], core[1])
        if k is None:
            raise ValueError(f'非法干支组合（不在六十甲子中）：{core}')
        return k + 1, f'干支第{k + 1}位', True
    if len(core) == 1:
        if core in STEMS:
            i = STEMS.index(core) + 1
            return i, f'天干第{i}', True
        if core in BRANCHES:
            i = BRANCHES.index(core) + 1
            return i, f'地支第{i}', True
        if core in ('零', '〇', '○'):
            return 0, '中文数字', False
    try:
        return cn_to_int(core), '中文数字', False
    except ValueError as exc:
        raise ValueError(f'无法识别的序号：{text.strip()!r}（{exc}）') from exc


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8')
            except Exception:
                pass
    ap = argparse.ArgumentParser(
        description='把「第十三条」「丙级」「辛丑」等中文序号解析回数值或序位')
    ap.add_argument('texts', nargs='+', help='中文序号，如 第十三条 / 丙级 / 辛丑')
    ap.add_argument('--0base', dest='zero_base', action='store_true',
                    help='天干/地支/干支序位改为 0 起算（辛丑 -> 37）')
    args = ap.parse_args(argv)

    failed = 0
    for item in args.texts:
        try:
            val, note, is_cycle = parse_one(item)
            if args.zero_base and is_cycle:
                val -= 1
                note += '（0起算）'
            print(f'{item.strip()} -> {val} ({note})')
        except ValueError as exc:
            print(f'hanzi-ordinal-parse: {exc}', file=sys.stderr)
            failed += 1
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
