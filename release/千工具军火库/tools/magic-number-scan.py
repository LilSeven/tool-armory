#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""魔法数字扫描 (magic-number-scan) —— 找出代码中未命名的大数值字面量。

扫描源码中的数字字面量(十进制/十六进制/二进制/八进制/浮点/科学计数/下划线
分隔均支持)，自动剔除字符串与注释里的数字，排除 0、1、-1 等常见值，且默认
只报告绝对值 >= --min(默认 10) 的值。全大写常量赋值行(如 MAX_SIZE = 1024、
const int MAX_SIZE = 1024、#define MAX_SIZE 1024) 视为"已命名"，不告警。
自动跳过二进制文件与常见无关目录(.git、node_modules 等)；单文件最多读 16MB。

示例:
  python magic-number-scan.py src/                  # 递归扫描目录
  python magic-number-scan.py a.py b.js             # 扫描指定文件
  python magic-number-scan.py . --min 100           # 只报告绝对值 >= 100 的值
  python magic-number-scan.py . --allow 60,255      # 额外放行指定值
  python magic-number-scan.py . --ext .py,.js       # 扫目录时限定扩展名
  python magic-number-scan.py . --fail-on-find      # 有告警则退出码 2 (CI 用)

退出码: 0 = 正常运行(无论是否发现告警); 2 = --fail-on-find 且发现告警;
        1 = 参数或路径错误。
仅用 Python 标准库，单文件。
"""

import argparse
import os
import re
import sys
from collections import Counter

MAX_READ = 16 * 1024 * 1024
DEFAULT_IGNORE_DIRS = {
    '.git', '.hg', '.svn', '__pycache__', 'node_modules', '.venv', 'venv',
    '.tox', '.mypy_cache', '.pytest_cache', '.idea', '.vscode',
}
DEFAULT_ALLOWED = {0, 1, -1}   # 常见值
DEFAULT_MIN = 10.0


def _rule(line, block, quotes, triple=()):
    return (tuple(line), tuple(tuple(p) for p in block), tuple(quotes),
            tuple(tuple(t) for t in triple))


_LANG_LIST = [
    (('.py', '.pyw', '.pyi'),
     _rule(('#',), (), ('"', "'"), (('"""',), ("'''",)))),
    (('.js', '.mjs', '.cjs', '.jsx', '.ts', '.tsx'),
     _rule(('//',), (('/*', '*/'),), ('"', "'", '`'))),
    (('.c', '.h', '.cc', '.cpp', '.cxx', '.hpp', '.hh', '.hxx', '.java', '.cs',
      '.go', '.rs', '.swift', '.kt', '.kts', '.scala', '.dart', '.php',
      '.m', '.mm'),
     _rule(('//',), (('/*', '*/'),), ('"', "'"))),
    (('.sh', '.bash', '.zsh', '.rb', '.r', '.jl', '.pl', '.pm',
      '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf'),
     _rule(('#',), (), ('"', "'"))),
    (('.sql',), _rule(('--',), (('/*', '*/'),), ("'",))),
    (('.lua',), _rule(('--',), (('--[[', ']]'),), ('"', "'"))),
]
LANG_RULES = {}
for _exts, _r in _LANG_LIST:
    for _e in _exts:
        LANG_RULES[_e] = _r
DEFAULT_RULE = _rule(('#', '//'), (), ('"', "'"))
DEFAULT_EXTS = frozenset(LANG_RULES)

NUM_RE = re.compile(
    r'(?<![\w.])'
    r'(-?)'
    r'(0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+'
    r'|\d[\d_]*(?:\.[\d_]+)?(?:[eE][+-]?\d+)?)'
    r'([uUlLfF]*)'
)
DEFINE_RE = re.compile(r'^\s*#\s*define\b')
_MODIFIERS = (
    r'const\s+|let\s+|var\s+|final\s+|val\s+|readonly\s+|static\s+|export\s+|'
    r'public\s+|private\s+|protected\s+|internal\s+|unsigned\s+|signed\s+|'
    r'uint8_t\s+|uint16_t\s+|uint32_t\s+|uint64_t\s+|int8_t\s+|int16_t\s+|'
    r'int32_t\s+|int64_t\s+|size_t\s+|int\s+|long\s+|short\s+|float\s+|'
    r'double\s+|bool\s+|boolean\s+|char\s+|auto\s+'
)
CONST_ASSIGN_RE = re.compile(
    r'^\s*(?:' + _MODIFIERS + r')*[A-Z][A-Z0-9_]{1,}\s*(?::\s*[^=;]+)?=(?!=)')


def mask_code(text, rules):
    """把字符串内容与注释替换为等长空格(保留换行)，保证行列号不变。"""
    line_comments, block_pairs, quotes, triples = rules
    out = list(text)
    n = len(text)

    def mask(i, ln):
        for k in range(i, min(i + ln, n)):
            if out[k] != '\n':
                out[k] = ' '

    i = 0
    state = None   # None | ('trip', d) | ('block', close) | ('str', q) | 'line'
    while i < n:
        c = text[i]
        if state is None:
            if c in '\r\n':
                i += 1
                continue
            hit = next((d for d in triples if text.startswith(d, i)), None)
            if hit:
                mask(i, len(hit)); state = ('trip', hit); i += len(hit); continue
            hit = next((p for p in block_pairs if text.startswith(p[0], i)), None)
            if hit:
                mask(i, len(hit[0])); state = ('block', hit[1]); i += len(hit[0]); continue
            if c in quotes:
                mask(i, 1); state = ('str', c); i += 1; continue
            hit = next((p for p in line_comments if text.startswith(p, i)), None)
            if hit:
                mask(i, len(hit)); state = 'line'; i += len(hit); continue
            i += 1
            continue
        kind = state[0] if isinstance(state, tuple) else state
        if kind == 'trip':
            d = state[1]
            if text.startswith(d, i):
                mask(i, len(d)); state = None; i += len(d); continue
            if c not in '\r\n':
                out[i] = ' '
            i += 1
            continue
        if kind == 'block':
            close = state[1]
            if text.startswith(close, i):
                mask(i, len(close)); state = None; i += len(close); continue
            if c not in '\r\n':
                out[i] = ' '
            i += 1
            continue
        if kind == 'str':
            if c == '\\':
                out[i] = ' '
                i += 1
                if i < n and text[i] != '\n':
                    out[i] = ' '
                    i += 1
                continue
            if c == state[1]:
                out[i] = ' '; state = None; i += 1; continue
            if c in '\r\n':
                state = None; i += 1; continue
            out[i] = ' '
            i += 1
            continue
        # 'line' 注释状态
        if c == '\n':
            state = None
        elif c != '\r':
            out[i] = ' '
        i += 1
    return ''.join(out)


def literal_value(sign, body):
    s = body.replace('_', '')
    try:
        low = s.lower()
        if low.startswith(('0x', '0b', '0o')):
            val = int(s, 0)
        elif '.' in s or 'e' in low:
            val = float(s)
        else:
            val = int(s)
    except ValueError:
        return None
    return -val if sign == '-' else val


def format_val(v):
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def iter_files(paths, exts, hidden, follow):
    ignore = DEFAULT_IGNORE_DIRS
    for p in paths:
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for root, dirs, files in os.walk(p, followlinks=follow):
                dirs[:] = sorted(
                    d for d in dirs
                    if d not in ignore and (hidden or not d.startswith('.')))
                for name in sorted(files):
                    if exts is not None:
                        e = os.path.splitext(name)[1].lower()
                        if e not in exts:
                            continue
                    yield os.path.join(root, name)


def scan_file(path, min_value, allowed):
    """返回 (findings, err)；findings 为 [(行号, 列号, 值, 上下文)]。"""
    try:
        with open(path, 'rb') as f:
            raw = f.read(MAX_READ + 1)
    except OSError as exc:
        return None, str(exc)
    if b'\x00' in raw[:4096]:
        return None, '__binary__'
    text = raw[:MAX_READ].decode('utf-8', 'replace')
    rules = LANG_RULES.get(os.path.splitext(path)[1].lower(), DEFAULT_RULE)
    masked = mask_code(text, rules)
    findings = []
    for lineno, (orig, m) in enumerate(zip(text.splitlines(), masked.splitlines()), 1):
        if not any(ch.isdigit() for ch in m):
            continue
        define_skip = DEFINE_RE.match(m) is not None
        const_m = CONST_ASSIGN_RE.match(m)
        const_from = const_m.end() if const_m else -1
        for mo in NUM_RE.finditer(m):
            if define_skip or (const_from >= 0 and mo.start() >= const_from):
                continue
            sign, body, _suffix = mo.groups()
            val = literal_value(sign, body)
            if val is None or val in allowed or abs(val) < min_value:
                continue
            ctx = orig.strip()
            if len(ctx) > 100:
                ctx = ctx[:97] + '...'
            findings.append((lineno, mo.start() + 1, val, ctx))
    findings.sort()
    return findings, None


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        prog='magic-number-scan',
        description='找出代码中未命名的大数值字面量(魔法数字)，排除 0、1、-1 等常见值。')
    parser.add_argument('paths', nargs='*', default=['.'],
                        help='要扫描的文件或目录，默认当前目录')
    parser.add_argument('--min', type=float, default=DEFAULT_MIN, metavar='N',
                        help='只报告绝对值 >= N 的字面量(默认 %(default)g)')
    parser.add_argument('--allow', default='', metavar='V1,V2',
                        help='额外放行的值，逗号分隔，如 60,255')
    parser.add_argument('--ext', default='', metavar='.PY,.JS',
                        help='扫描目录时只处理这些扩展名(默认覆盖常见代码语言)')
    parser.add_argument('--hidden', action='store_true',
                        help='同时进入 . 开头的隐藏目录(常见无关目录仍会跳过)')
    parser.add_argument('--follow-symlinks', action='store_true',
                        help='跟随目录符号链接')
    parser.add_argument('--fail-on-find', action='store_true',
                        help='发现告警时以退出码 2 结束(CI 用)')
    args = parser.parse_args(argv)

    allowed = set(DEFAULT_ALLOWED)
    for tok in re.split(r'[,\s]+', args.allow.strip()):
        if not tok:
            continue
        try:
            allowed.add(int(tok, 0))
        except ValueError:
            try:
                allowed.add(float(tok))
            except ValueError:
                print('错误: --allow 的值无效: %r' % tok, file=sys.stderr)
                return 1

    exts = DEFAULT_EXTS
    if args.ext.strip():
        exts = {(e if e.startswith('.') else '.' + e).lower()
                for e in re.split(r'[,\s]+', args.ext.strip()) if e}

    missing = [p for p in args.paths if not os.path.exists(p)]
    if missing:
        print('错误: 路径不存在: %s' % ', '.join(missing), file=sys.stderr)
        return 1

    files_scanned = skipped_binary = total = 0
    errors = []
    results = []
    value_counter = Counter()
    for path in iter_files(args.paths, exts, args.hidden, args.follow_symlinks):
        findings, err = scan_file(path, args.min, allowed)
        if err == '__binary__':
            skipped_binary += 1
            continue
        if err:
            errors.append((path, err))
            continue
        files_scanned += 1
        if findings:
            results.append((path, findings))
            total += len(findings)
            for _ln, _col, val, _ctx in findings:
                value_counter[val] += 1

    for path, findings in results:
        for lineno, col, val, ctx in findings:
            print('%s:%d:%d: 值 %s  |  %s' % (path, lineno, col, format_val(val), ctx))
    dist = '  '.join('%s×%d' % (format_val(v), c) for v, c in
                     sorted(value_counter.items(), key=lambda kv: (-kv[1], kv[0])))
    print('-- 扫描 %d 个文件(跳过二进制 %d)，发现魔法数字 %d 处 --'
          % (files_scanned, skipped_binary, total))
    if dist:
        print('按值分布: %s' % dist)
    for path, err in errors:
        print('警告: 跳过 %s: %s' % (path, err), file=sys.stderr)
    if args.fail_on_find and total:
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
