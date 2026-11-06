#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分节符混用检查（wan-section-lint）。

检查文档中数字分节符的两种风格是否混用、以及分节符位置是否错误，并定位行号：

  千分位    每节 3 位（英文式）：1,234,567 / 12,345
  万进制    每节 4 位（中文万进制）：1,2345,6789 / 123,4567
  位置错误  各节长度既不满足千分位也不满足万进制：12,34,567 / 1,23,456

同一文档同时出现千分位与万进制时给出「混用」提醒。全角逗号「，」按「,」
处理；形如 1,2,3、10,20,30 的短枚举按列表跳过，不视为数字。
已知局限：形如「2023,2024年」的年份列举会被当作万进制数字，属可容忍误报。

用法：
    python wan-section-lint.py FILE [FILE ...] [--show-ok] [--strict]
    cat FILE | python wan-section-lint.py -            # 从 stdin 读
    python wan-section-lint.py --demo                  # 内置示例演示

退出码：0 = 正常完成（无论是否发现问题）；1 = --strict 且发现问题；
        2 = 用法或文件读取错误。

示例命令：
    python wan-section-lint.py report.txt
    python wan-section-lint.py report.txt --strict
"""

import argparse
import re
import sys

TOKEN_RE = re.compile(r'(?<![0-9.,])([0-9]{1,4}(?:[,，][0-9]+)+)(?![0-9])')

THOUSANDS, WAN, BAD, ENUM = 'thousands', 'wan', 'bad', 'enum'


def classify(token: str) -> str:
    """按各节宽度把分节数字归为千分位/万进制/位置错误/枚举。"""
    groups = token.replace('，', ',').split(',')
    lens = [len(g) for g in groups]
    if len(lens) >= 3 and all(l <= 2 for l in lens):
        return ENUM  # 1,2,3 / 10,20,30 之类的列举
    rest = lens[1:]
    if all(l == 3 for l in rest) and lens[0] <= 3:
        return THOUSANDS
    if all(l == 4 for l in rest) and lens[0] <= 4:
        return WAN
    return BAD


def scan_text(text: str):
    """逐行扫描，返回 [(行号, 风格, 原文 token), ...]。"""
    out = []
    for no, line in enumerate(text.splitlines(), 1):
        for m in TOKEN_RE.finditer(line):
            st = classify(m.group(1))
            if st != ENUM:
                out.append((no, st, m.group(1)))
    return out


DEMO_TEXT = """2025年度公司营收为1,234,567元，较上年增长8%。
项目总投入1,2345,6789元，其中设备款12,34,567元待核。
合同编号No.2025-0089，保证金8,912元。
参会名单：1,2,3号与10,20,30号均已签到。
"""


def report(name: str, findings, show_ok: bool = False) -> None:
    """打印检查报告：位置错误、两种风格的分布与汇总。"""
    counts = {THOUSANDS: 0, WAN: 0, BAD: 0}
    for _, st, _tok in findings:
        if st in counts:
            counts[st] += 1
    for no, st, tok in findings:
        if st == BAD:
            print(f'{name}:{no}: [位置错误] 「{tok}」 各节长度既非千分位亦非万进制')
        elif st == THOUSANDS and (show_ok or counts[WAN]):
            print(f'{name}:{no}: [千分位] 「{tok}」')
        elif st == WAN and (show_ok or counts[THOUSANDS]):
            print(f'{name}:{no}: [万进制] 「{tok}」')
    if counts[THOUSANDS] and counts[WAN]:
        print(f'{name}: [混用] 千分位 {counts[THOUSANDS]} 处与万进制 '
              f'{counts[WAN]} 处同时出现，建议统一分节风格')
    if counts[THOUSANDS] or counts[WAN] or counts[BAD]:
        print(f'{name}: 汇总：千分位 {counts[THOUSANDS]} 处，万进制 {counts[WAN]} 处，'
              f'位置错误 {counts[BAD]} 处')
    else:
        print(f'{name}: 未发现分节符问题')


def decode_data(data: bytes) -> str:
    """依次尝试 utf-8-sig / utf-8 / gbk 解码，最后兜底替换。"""
    for enc in ('utf-8-sig', 'utf-8', 'gbk'):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', errors='replace')


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8')
            except Exception:
                pass
    ap = argparse.ArgumentParser(
        description='检查文档中千分位与万进制分节混用、分节符位置错误并定位行号')
    ap.add_argument('files', nargs='*', help='待检查的文本文件，「-」表示 stdin')
    ap.add_argument('--show-ok', action='store_true',
                    help='同时列出所有正常分节的数字（默认仅在混用时列出）')
    ap.add_argument('--strict', action='store_true', help='发现问题时退出码置 1')
    ap.add_argument('--demo', action='store_true', help='用内置示例演示检查效果')
    args = ap.parse_args(argv)

    if args.demo:
        report('<demo>', scan_text(DEMO_TEXT), args.show_ok)
        return 0
    if not args.files:
        ap.error('至少提供一个文件，或使用 --demo')

    any_problem = False
    for path in args.files:
        try:
            if path == '-':
                text = decode_data(sys.stdin.buffer.read())
                name = '<stdin>'
            else:
                with open(path, 'rb') as fh:
                    text = decode_data(fh.read())
                name = path
        except OSError as exc:
            print(f'wan-section-lint: 无法读取 {path}：{exc}', file=sys.stderr)
            return 2
        findings = scan_text(text)
        report(name, findings, args.show_ok)
        n_bad = sum(1 for _, st, _ in findings if st == BAD)
        n_th = sum(1 for _, st, _ in findings if st == THOUSANDS)
        n_wan = sum(1 for _, st, _ in findings if st == WAN)
        if n_bad or (n_th and n_wan):
            any_problem = True
    return 1 if (args.strict and any_problem) else 0


if __name__ == '__main__':
    sys.exit(main())
