#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TODO按人分组 (todo-by-owner) —— 识别 TODO(user) 形式的负责人标记，按人归组输出各自待办清单。

匹配 `TODO(负责人)`、`FIXME(负责人)`、`XXX(负责人)`、`HACK(负责人)`
四种带负责人的标记(兼容标记与括号间的空格，负责人名按大小写不敏感归组)，
按人归组输出 `文件:行号: [类型] 内容`；无负责人的标记单独计数，
可用 --show-unassigned 查看明细。自动跳过二进制文件与常见无关目录。

示例:
  python todo-by-owner.py src/                 # 按人归组列出待办
  python todo-by-owner.py                      # 扫描当前目录
  python todo-by-owner.py . --owner alice      # 只看 alice 的待办
  python todo-by-owner.py . --show-unassigned  # 同时列出无负责人的标记
  python todo-by-owner.py . -i                 # 标记大小写不敏感(todo(alice) 也算)

退出码: 0 = 正常; 1 = 参数或路径错误。
仅用 Python 标准库，单文件。
"""

import argparse
import os
import re
import sys

MAX_READ = 4 * 1024 * 1024
MARKERS = ('TODO', 'FIXME', 'XXX', 'HACK')
DEFAULT_IGNORE_DIRS = {
    '.git', '.hg', '.svn', '__pycache__', 'node_modules', '.venv', 'venv',
    '.tox', '.mypy_cache', '.pytest_cache', '.idea', '.vscode',
}

OWNER_RE = re.compile(r'\b(TODO|FIXME|XXX|HACK)\s*\(\s*([^()\n]{1,80}?)\s*\)')
UNASSIGNED_RE = re.compile(r'\b(?:TODO|FIXME|XXX|HACK)\b(?!\s*\()')


def build_re(case_insensitive):
    flags = re.IGNORECASE if case_insensitive else 0
    return (re.compile(OWNER_RE.pattern, flags),
            re.compile(UNASSIGNED_RE.pattern, flags))


def iter_files(paths, hidden, follow):
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
                    yield os.path.join(root, name)


def scan_file(path, owner_re, unassigned_re, max_len):
    """返回 (owner_hits, unassigned_hits, err)。

    owner_hits: [(行号, 类型, 负责人, 内容)]; unassigned_hits: [(行号, 类型, 内容)]
    """
    try:
        with open(path, 'rb') as f:
            raw = f.read(MAX_READ + 1)
    except OSError as exc:
        return None, None, str(exc)
    if b'\x00' in raw[:4096]:
        return None, None, '__binary__'
    text = raw[:MAX_READ].decode('utf-8', 'replace')

    def tail(line, end):
        rest = line[end:].lstrip(' \t:：-–—=>*').strip()
        if len(rest) > max_len:
            rest = rest[:max_len - 3] + '...'
        return rest

    owner_hits, unassigned_hits = [], []
    for lineno, line in enumerate(text.splitlines(), 1):
        for mo in owner_re.finditer(line):
            owner = mo.group(2).strip()
            if owner:
                owner_hits.append(
                    (lineno, mo.group(1).upper(), owner, tail(line, mo.end())))
        for mo in unassigned_re.finditer(line):
            unassigned_hits.append((lineno, mo.group(0).upper(), tail(line, mo.end())))
    return owner_hits, unassigned_hits, None


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        prog='todo-by-owner',
        description='识别 TODO(user) 形式的负责人标记，按人归组输出各自待办清单。')
    parser.add_argument('paths', nargs='*', default=['.'],
                        help='要扫描的文件或目录，默认当前目录')
    parser.add_argument('--owner', default='', metavar='NAME',
                        help='只看指定负责人的待办(大小写不敏感)')
    parser.add_argument('--show-unassigned', action='store_true',
                        help='同时列出无负责人(裸 TODO/FIXME/XXX/HACK)的标记')
    parser.add_argument('-i', '--ignore-case', action='store_true',
                        help='标记大小写不敏感(todo(alice) 也算)')
    parser.add_argument('--max-len', type=int, default=120, metavar='N',
                        help='每条内容最多显示 N 个字符(默认 %(default)s)')
    parser.add_argument('--hidden', action='store_true',
                        help='同时进入 . 开头的隐藏目录(常见无关目录仍会跳过)')
    parser.add_argument('--follow-symlinks', action='store_true',
                        help='跟随目录符号链接')
    args = parser.parse_args(argv)

    owner_filter = args.owner.strip().lower() or None
    missing = [p for p in args.paths if not os.path.exists(p)]
    if missing:
        print('错误: 路径不存在: %s' % ', '.join(missing), file=sys.stderr)
        return 1

    owner_re, unassigned_re = build_re(args.ignore_case)
    groups = {}          # key=负责人小写 -> {'name': 显示名, 'items': [...]}
    unassigned_all = []
    owner_total = 0
    errors = []
    for path in iter_files(args.paths, args.hidden, args.follow_symlinks):
        owner_hits, unassigned_hits, err = scan_file(
            path, owner_re, unassigned_re, args.max_len)
        if err == '__binary__':
            continue
        if err:
            errors.append((path, err))
            continue
        for lineno, kind, owner, text in owner_hits:
            key = owner.lower()
            g = groups.setdefault(key, {'name': owner, 'items': []})
            g['items'].append((path, lineno, kind, text))
            owner_total += 1
        unassigned_all.extend((path,) + h for h in unassigned_hits)

    ordered = sorted(groups.values(),
                     key=lambda g: (-len(g['items']), g['name'].lower()))
    shown = 0
    for g in ordered:
        if owner_filter and g['name'].lower() != owner_filter:
            continue
        print('== %s (%d) ==' % (g['name'], len(g['items'])))
        for path, lineno, kind, text in g['items']:
            print('  %s:%d: [%s] %s' % (path, lineno, kind, text))
        print()
        shown += len(g['items'])

    if owner_filter:
        if shown == 0:
            print('没有找到负责人 %r 的标记。' % args.owner.strip())
    else:
        if owner_filter is None and args.show_unassigned and unassigned_all:
            print('== 未分配负责人 (%d) ==' % len(unassigned_all))
            for path, lineno, kind, text in unassigned_all:
                print('  %s:%d: [%s] %s' % (path, lineno, kind, text))
            print()
        print('-- 共 %d 位负责人, %d 处带负责人标记, %d 处未分配 --'
              % (len(groups), owner_total, len(unassigned_all)))
    for path, err in errors:
        print('警告: 跳过 %s: %s' % (path, err), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
