#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TODO全仓扫描 (todo-scanner) —— 扫描 TODO/FIXME/XXX/HACK 标记，输出带文件行号的清单。

递归扫描目录(默认当前目录)中的文本文件，找出 TODO / FIXME / XXX / HACK
四类标记，输出 `文件:行号: [类型] 标记后的内容` 清单与分类统计；
支持按类型过滤、大小写不敏感匹配；自动跳过二进制文件与常见无关目录
(.git、node_modules 等)；单文件最多读取 4MB。

示例:
  python todo-scanner.py src/                # 扫描目录
  python todo-scanner.py                     # 扫描当前目录
  python todo-scanner.py . -t FIXME,TODO     # 只看 FIXME 与 TODO
  python todo-scanner.py . -i                # 大小写不敏感(小写 todo 也算)
  python todo-scanner.py a.py b.py           # 扫描指定文件
  python todo-scanner.py . --fail-on-find    # 发现标记则退出码 2 (CI 用)

退出码: 0 = 正常; 2 = --fail-on-find 且发现标记; 1 = 参数或路径错误。
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


def build_marker_re(case_insensitive):
    pattern = r'\b(%s)\b' % '|'.join(MARKERS)
    return re.compile(pattern, re.IGNORECASE if case_insensitive else 0)


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


def scan_file(path, marker_re, max_len):
    """返回 (hits, err)；hits 为 [(行号, 类型, 标记后文本)]。"""
    try:
        with open(path, 'rb') as f:
            raw = f.read(MAX_READ + 1)
    except OSError as exc:
        return None, str(exc)
    if b'\x00' in raw[:4096]:
        return None, '__binary__'
    text = raw[:MAX_READ].decode('utf-8', 'replace')
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for mo in marker_re.finditer(line):
            kind = mo.group(1).upper()
            rest = line[mo.end():].lstrip(' \t:：-–—=>*')
            rest = rest.strip()
            if len(rest) > max_len:
                rest = rest[:max_len - 3] + '...'
            hits.append((lineno, kind, rest))
    return hits, None


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        prog='todo-scanner',
        description='扫描 TODO/FIXME/XXX/HACK 标记，输出带文件行号的清单，支持按类型过滤。')
    parser.add_argument('paths', nargs='*', default=['.'],
                        help='要扫描的文件或目录，默认当前目录')
    parser.add_argument('-t', '--type', dest='types', action='append',
                        default=[], metavar='TYPE[,TYPE2]',
                        help='只看这些类型(逗号分隔，可多次给出)，如 FIXME,TODO')
    parser.add_argument('-i', '--ignore-case', action='store_true',
                        help='大小写不敏感(小写 todo 也算)')
    parser.add_argument('--max-len', type=int, default=120, metavar='N',
                        help='每条内容最多显示 N 个字符(默认 %(default)s)')
    parser.add_argument('--hidden', action='store_true',
                        help='同时进入 . 开头的隐藏目录(常见无关目录仍会跳过)')
    parser.add_argument('--follow-symlinks', action='store_true',
                        help='跟随目录符号链接')
    parser.add_argument('--fail-on-find', action='store_true',
                        help='发现标记时以退出码 2 结束(CI 用)')
    args = parser.parse_args(argv)

    wanted = None
    if args.types:
        wanted = []
        for chunk in args.types:
            for tok in re.split(r'[,\s]+', chunk.strip()):
                if not tok:
                    continue
                up = tok.upper()
                if up not in MARKERS:
                    print('错误: 未知类型 %r，可选: %s' % (tok, '/'.join(MARKERS)),
                          file=sys.stderr)
                    return 1
                if up not in wanted:
                    wanted.append(up)

    missing = [p for p in args.paths if not os.path.exists(p)]
    if missing:
        print('错误: 路径不存在: %s' % ', '.join(missing), file=sys.stderr)
        return 1

    marker_re = build_marker_re(args.ignore_case)
    files_scanned = skipped_binary = total = 0
    counter = {}
    errors = []
    results = []
    for path in iter_files(args.paths, args.hidden, args.follow_symlinks):
        hits, err = scan_file(path, marker_re, args.max_len)
        if err == '__binary__':
            skipped_binary += 1
            continue
        if err:
            errors.append((path, err))
            continue
        files_scanned += 1
        if wanted:
            hits = [h for h in hits if h[1] in wanted]
        if hits:
            results.append((path, hits))
            total += len(hits)
            for _ln, kind, _txt in hits:
                counter[kind] = counter.get(kind, 0) + 1

    for path, hits in results:
        for lineno, kind, text in hits:
            print('%s:%d: [%s] %s' % (path, lineno, kind, text))
    dist = '  '.join('%s×%d' % kv for kv in
                     sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))
    print('-- 扫描 %d 个文件(跳过二进制 %d)，命中标记 %d 处 --'
          % (files_scanned, skipped_binary, total))
    if dist:
        print('按类型: %s' % dist)
    elif wanted:
        print('按类型: 所选类型 %s 均无命中' % '/'.join(wanted))
    for path, err in errors:
        print('警告: 跳过 %s: %s' % (path, err), file=sys.stderr)
    if args.fail_on_find and total:
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
