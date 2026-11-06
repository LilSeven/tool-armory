#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""带日期TODO检查 (todo-dated) —— 提取 TODO 中标注的日期(如 TODO@2026-01-01)，列出已逾期项。

识别 `TODO@YYYY-MM-DD`、`FIXME@YYYY-MM-DD`、`XXX@YYYY-MM-DD`、
`HACK@YYYY-MM-DD` 四种带截止日期的标记(日期须为合法的 ISO 格式)，
与基准日期(默认今天，可用 --today 指定)比较后分组输出:
已逾期 / 今日到期 / 未来 N 天内到期 / 更远的未来。
日期非法(如 2026-13-99)的标记忽略并计数；不带日期的标记不参与统计。
自动跳过二进制文件与常见无关目录。

示例:
  python todo-dated.py src/                     # 以今天为基准检查逾期
  python todo-dated.py . --today 2026-01-01     # 指定基准日期(便于回溯/测试)
  python todo-dated.py . --within 30            # 额外列出未来 30 天内到期项
  python todo-dated.py . --all                  # 列出所有带日期项
  python todo-dated.py . --fail-on-overdue      # 有逾期项则退出码 2 (CI 用)

退出码: 0 = 正常; 2 = --fail-on-overdue 且存在逾期项; 1 = 参数或路径错误。
仅用 Python 标准库，单文件。
"""

import argparse
import os
import re
import sys
from datetime import date

MAX_READ = 4 * 1024 * 1024
MARKERS = ('TODO', 'FIXME', 'XXX', 'HACK')
DEFAULT_IGNORE_DIRS = {
    '.git', '.hg', '.svn', '__pycache__', 'node_modules', '.venv', 'venv',
    '.tox', '.mypy_cache', '.pytest_cache', '.idea', '.vscode',
}

DATED_RE = re.compile(r'\b(TODO|FIXME|XXX|HACK)@(\d{4}-\d{2}-\d{2})')


def build_re(case_insensitive):
    return re.compile(DATED_RE.pattern,
                      re.IGNORECASE if case_insensitive else 0)


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


def scan_file(path, dated_re, max_len):
    """返回 (hits, err)；hits 为 [(行号, 类型, date, 内容)]。"""
    try:
        with open(path, 'rb') as f:
            raw = f.read(MAX_READ + 1)
    except OSError as exc:
        return None, str(exc)
    if b'\x00' in raw[:4096]:
        return None, '__binary__'
    text = raw[:MAX_READ].decode('utf-8', 'replace')
    hits, invalid = [], 0
    for lineno, line in enumerate(text.splitlines(), 1):
        for mo in dated_re.finditer(line):
            try:
                due = date.fromisoformat(mo.group(2))
            except ValueError:
                invalid += 1
                continue
            rest = line[mo.end():].lstrip(' \t:：-–—=>*').strip()
            if len(rest) > max_len:
                rest = rest[:max_len - 3] + '...'
            hits.append((lineno, mo.group(1).upper(), due, rest))
    return (hits, invalid), None


def emit(title, items, today, note):
    if not items:
        return
    print('== %s (%d) ==' % (title, len(items)))
    for due, path, lineno, kind, text in items:
        if note == 'today':
            mark = '今天到期'
        else:
            mark = (note % abs((due - today).days))
        print('  %s:%d: [%s@%s] %s  (%s)'
              % (path, lineno, kind, due.isoformat(), text, mark))
    print()


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        prog='todo-dated',
        description='提取 TODO@2026-01-01 形式的截止日期，与基准日期比较并列出已逾期项。')
    parser.add_argument('paths', nargs='*', default=['.'],
                        help='要扫描的文件或目录，默认当前目录')
    parser.add_argument('--today', default='', metavar='YYYY-MM-DD',
                        help='基准日期(默认为今天的系统日期)')
    parser.add_argument('--within', type=int, default=0, metavar='N',
                        help='额外列出未来 N 天内到期的项')
    parser.add_argument('--all', action='store_true',
                        help='列出所有带日期的标记(含更远的未来)')
    parser.add_argument('-i', '--ignore-case', action='store_true',
                        help='标记大小写不敏感(todo@2026-01-01 也算)')
    parser.add_argument('--max-len', type=int, default=120, metavar='N',
                        help='每条内容最多显示 N 个字符(默认 %(default)s)')
    parser.add_argument('--hidden', action='store_true',
                        help='同时进入 . 开头的隐藏目录(常见无关目录仍会跳过)')
    parser.add_argument('--follow-symlinks', action='store_true',
                        help='跟随目录符号链接')
    parser.add_argument('--fail-on-overdue', action='store_true',
                        help='存在逾期项时以退出码 2 结束(CI 用)')
    args = parser.parse_args(argv)

    today = date.today()
    if args.today:
        try:
            today = date.fromisoformat(args.today)
        except ValueError:
            print('错误: --today 需为有效的 YYYY-MM-DD 日期，收到 %r' % args.today,
                  file=sys.stderr)
            return 1

    missing = [p for p in args.paths if not os.path.exists(p)]
    if missing:
        print('错误: 路径不存在: %s' % ', '.join(missing), file=sys.stderr)
        return 1

    dated_re = build_re(args.ignore_case)
    overdue, due_today, future = [], [], []
    total = invalid = 0
    errors = []
    for path in iter_files(args.paths, args.hidden, args.follow_symlinks):
        res, err = scan_file(path, dated_re, args.max_len)
        if err == '__binary__':
            continue
        if err:
            errors.append((path, err))
            continue
        hits, bad = res
        invalid += bad
        total += len(hits)
        for lineno, kind, due, text in hits:
            delta = (due - today).days
            item = (due, path, lineno, kind, text)
            if delta < 0:
                overdue.append(item)
            elif delta == 0:
                due_today.append(item)
            else:
                future.append(item)

    key = lambda it: (it[0], it[1], it[2])
    overdue.sort(key=key)
    due_today.sort(key=key)
    future.sort(key=key)

    emit('已逾期', overdue, today, '逾期 %d 天')
    emit('今日到期', due_today, today, 'today')
    near = far = []
    if future:
        if args.within > 0:
            near = [it for it in future if (it[0] - today).days <= args.within]
            far = [it for it in future if (it[0] - today).days > args.within]
            emit('未来 %d 天内到期' % args.within, near, today, '还剩 %d 天')
            if args.all:
                emit('更远的未来', far, today, '还剩 %d 天')
        elif args.all:
            emit('未来', future, today, '还剩 %d 天')
    print('-- 基准日期 %s: 带日期标记 %d 处 —— 已逾期 %d, 今日到期 %d, 未来 %d; '
          '无效日期 %d 处(已忽略) --'
          % (today.isoformat(), total, len(overdue), len(due_today),
             len(future), invalid))
    if not (args.all or args.within > 0) and future:
        print('提示: 加 --all 或 --within N 可查看未来到期的明细')
    for path, err in errors:
        print('警告: 跳过 %s: %s' % (path, err), file=sys.stderr)
    if args.fail_on_overdue and overdue:
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
