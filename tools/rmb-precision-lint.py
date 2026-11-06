#!/usr/bin/env python3
"""金额精度检查(rmb-precision-lint)。

检查文本中金额的精度问题并汇总报告(仅把带货币语义的数字视为金额):
    1. 小数超过两位(如 ¥12.345)                -> ERROR
    2. 只有一位小数(如 1000.5元, 金额惯例两位)  -> WARN
    3. 同一文件内「无小数位」与「两位小数」混用  -> WARN(风格不一致)

用法:
    python rmb-precision-lint.py 文件或目录... [-o 报告.md] [--json] [--strict]

示例:
    python -I rmb-precision-lint.py ./docs
    python -I rmb-precision-lint.py a.txt b.md
    python -I rmb-precision-lint.py ./docs --strict   # 发现问题时退出码 1(CI 用)

默认退出码 0 表示「检查过程正常完成」(是否发现问题见报告);
--strict 下出现 ERROR/WARN 时退出码为 1。
扫描目录时按常见文本扩展名筛选, 编码按 UTF-8/GB18030 自动尝试。
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

DEFAULT_EXTS = ('.txt', '.md', '.markdown', '.rst', '.csv', '.log',
                '.ini', '.cfg', '.tex', '.json', '.xml', '.html')
SKIP_DIRS = {'.git', '.hg', '.svn', 'node_modules', '__pycache__',
             '.venv', 'venv', '.idea', '.vscode'}

# ---------------- 金额匹配(保留完整小数位以检查精度) ----------------
_NUM = r'(?:\d{1,3}(?:,\d{3})+|\d+)'
RE_PREFIXED = re.compile(
    r'(?<![A-Za-z])(?:[¥￥]|RMB|人民币)\s?(?P<num>' + _NUM + r')(?:\.(?P<frac>\d+))?', re.I)
RE_SUFFIXED = re.compile(
    r'(?P<num>' + _NUM + r')(?:\.(?P<frac>\d+))?(?P<wan>万)?(?:块钱|块|元|圆)')


def iter_amounts(line):
    """一行 -> [(start, end, 原文, 小数字符串或None), ...]; 重叠匹配保留更早/更长的一个"""
    found = []
    for m in RE_PREFIXED.finditer(line):
        found.append((m.start(), m.end(), m.group(0), m.group('frac')))
    for m in RE_SUFFIXED.finditer(line):
        found.append((m.start(), m.end(), m.group(0), m.group('frac')))
    found.sort(key=lambda t: (t[0], -t[1]))
    out, last_end = [], -1
    for item in found:
        if item[0] >= last_end:
            out.append(item)
            last_end = item[1]
    return out


def lint_text(text):
    """单文件检查 -> (金额处数, errors[(行,消息)], warns[(行或None,消息)], 风格计数)"""
    errors, warns = [], []
    occ = 0
    style_count = Counter()
    for lineno, line in enumerate(text.splitlines(), 1):
        for _s, _e, raw, frac in iter_amounts(line):
            occ += 1
            flen = len(frac) if frac is not None else 0
            if flen > 2:
                errors.append((lineno, '金额"%s" 有%d位小数, 超过两位' % (raw, flen)))
            elif flen == 1:
                warns.append((lineno, '金额"%s" 仅1位小数, 金额惯例保留两位' % raw))
                style_count[1] += 1
            else:
                style_count[flen] += 1
    if style_count[0] and style_count[2]:
        warns.append((None, '小数位风格不一致: 无小数位×%d 与 两位小数×%d 混用'
                      % (style_count[0], style_count[2])))
    return occ, errors, warns, dict(style_count)


def read_text(path):
    with open(path, 'rb') as fh:
        raw = fh.read()
    for enc in ('utf-8-sig', 'utf-8', 'gb18030'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def collect_files(paths, exts):
    files = []
    for p in paths:
        if os.path.isdir(p):
            for dirpath, dirnames, filenames in os.walk(p):
                dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
                for name in sorted(filenames):
                    if os.path.splitext(name)[1].lower() in exts:
                        files.append(os.path.join(dirpath, name))
        elif os.path.isfile(p):
            files.append(p)
        else:
            print('警告: 路径不存在, 跳过: %s' % p, file=sys.stderr)
    return sorted(files)


def build_report(results):
    lines = ['== 金额精度检查报告 ==', '']
    total_err = total_warn = total_occ = 0
    for r in results:
        lines.append('文件: %s' % r['path'])
        if not r['errors'] and not r['warns']:
            lines.append('  (无精度问题, 金额 %d 处)' % r['occurrences'])
        for ln, msg in r['errors']:
            loc = '行%d: ' % ln if ln else ''
            lines.append('  [ERROR] %s%s' % (loc, msg))
        for ln, msg in r['warns']:
            loc = '行%d: ' % ln if ln else ''
            lines.append('  [WARN]  %s%s' % (loc, msg))
        lines.append('')
        total_err += len(r['errors'])
        total_warn += len(r['warns'])
        total_occ += r['occurrences']
    lines.append('汇总: 检查 %d 个文件, 金额 %d 处; ERROR %d, WARN %d'
                 % (len(results), total_occ, total_err, total_warn))
    return '\n'.join(lines), total_err, total_warn


def build_json(results):
    return {
        'files': [{'path': r['path'], 'occurrences': r['occurrences'],
                   'errors': [{'line': ln, 'message': msg} for ln, msg in r['errors']],
                   'warnings': [{'line': ln, 'message': msg} for ln, msg in r['warns']],
                   'styles': r['styles']} for r in results],
        'summary': {
            'files_checked': len(results),
            'occurrences': sum(r['occurrences'] for r in results),
            'errors': sum(len(r['errors']) for r in results),
            'warnings': sum(len(r['warns']) for r in results),
        },
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
        description='检查文本中金额的精度问题(超过两位小数/小数位风格不一致等)')
    ap.add_argument('paths', nargs='+', help='要检查的文件或目录')
    ap.add_argument('-o', '--output', help='报告输出文件(默认打印到 stdout)')
    ap.add_argument('--json', action='store_true', help='以 JSON 输出')
    ap.add_argument('--strict', action='store_true',
                    help='发现 ERROR/WARN 时退出码 1(默认始终 0)')
    args = ap.parse_args(argv)

    exts = {e.lower() for e in DEFAULT_EXTS}
    files = collect_files(args.paths, exts)
    results = []
    for path in files:
        text = read_text(path)
        if text is None:
            print('警告: 无法解码, 跳过: %s' % path, file=sys.stderr)
            continue
        occ, errors, warns, styles = lint_text(text)
        results.append({'path': path.replace('\\', '/'), 'occurrences': occ,
                        'errors': errors, 'warns': warns, 'styles': styles})

    if args.json:
        print(json.dumps(build_json(results), ensure_ascii=False, indent=2))
        total_err = sum(len(r['errors']) for r in results)
        total_warn = sum(len(r['warns']) for r in results)
    else:
        report, total_err, total_warn = build_report(results)
        if args.output:
            with open(args.output, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(report.rstrip('\n') + '\n')
            print('报告已写入: %s' % args.output)
        else:
            print(report)

    if args.strict and (total_err or total_warn):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
