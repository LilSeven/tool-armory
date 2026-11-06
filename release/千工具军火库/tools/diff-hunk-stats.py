#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diff-hunk-stats.py —— hunk 粒度统计：统计 diff 中每个 hunk 的增删行数并按幅度排序。

用途
    解析 unified diff，对每个 hunk 统计 +行数、-行数和总改动行数，
    默认按总改动幅度从大到小排序，用于快速定位最大的改动；
    另附整体汇总，也可输出 JSON 供脚本处理。

用法
    python diff-hunk-stats.py [输入diff] [--sort total|added|removed|file]
                              [--asc] [--top N] [--json]
    输入为 '-' 或省略时读 stdin。

示例
    python diff-hunk-stats.py changes.patch
    python diff-hunk-stats.py changes.patch --sort added --top 5
    git diff | python diff-hunk-stats.py --json

输出列
    FILE 文件 | HUNK hunk头 | +ADD 新增 | -DEL 删除 | TOTAL 总改动 | PREVIEW 首个改动行

退出码
    0 成功；1 输入中没有可识别的 unified diff；2 读文件/参数错误。
"""
import argparse
import json
import re
import sys

HUNK_HEADER_RE = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$')


class Hunk(object):
    __slots__ = ('header', 'old_start', 'old_count', 'new_start', 'new_count',
                 'section', 'lines')

    def __init__(self, header, old_start, old_count, new_start, new_count, section):
        self.header = header
        self.old_start = old_start
        self.old_count = old_count
        self.new_start = new_start
        self.new_count = new_count
        self.section = section
        self.lines = []


class FileDiff(object):
    __slots__ = ('header', 'old_path', 'new_path', 'hunks')

    def __init__(self):
        self.header = []
        self.old_path = ''
        self.new_path = ''
        self.hunks = []

    @property
    def path(self):
        if self.new_path and self.new_path != '/dev/null':
            return self.new_path
        return self.old_path


def clean_path(raw):
    """从 '--- ' / '+++ ' 行内容取出纯路径：去时间戳、引号与 a/ b/ 前缀。"""
    p = raw.split('\t', 1)[0].strip()
    if len(p) >= 2 and p.startswith('"') and p.endswith('"'):
        p = p[1:-1]
    if p == '/dev/null':
        return p
    if len(p) > 2 and p[:2] in ('a/', 'b/'):
        p = p[2:]
    return p


def parse_unified_diff(text):
    """把 unified diff 文本解析成 FileDiff 列表（尽力而为：坏行忽略）。"""
    lines = text.splitlines()
    files = []
    cur = None
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        starts_paths = (line.startswith('--- ')
                        and i + 1 < n and lines[i + 1].startswith('+++ '))
        if line.startswith('diff '):
            cur = FileDiff()
            files.append(cur)
        elif starts_paths and (cur is None or cur.old_path or cur.new_path):
            # 纯 GNU diff 没有 "diff " 前导行，或上一文件段已完整时另起新段；
            # 否则 ---/+++ 属于当前 "diff " 段的文件头
            cur = FileDiff()
            files.append(cur)
        if cur is None:
            i += 1
            continue
        if starts_paths:
            cur.header.append(line)
            cur.old_path = clean_path(line[4:])
            cur.header.append(lines[i + 1])
            cur.new_path = clean_path(lines[i + 1][4:])
            i += 2
            continue
        m = HUNK_HEADER_RE.match(line)
        if m:
            hunk = Hunk(line, int(m.group(1)),
                        int(m.group(2)) if m.group(2) is not None else 1,
                        int(m.group(3)),
                        int(m.group(4)) if m.group(4) is not None else 1,
                        m.group(5).strip())
            i += 1
            old_left, new_left = hunk.old_count, hunk.new_count
            while i < n and (old_left > 0 or new_left > 0):
                body = lines[i]
                tag = body[:1]
                if tag == '\\':
                    hunk.lines.append(body)
                    i += 1
                    continue
                if tag == ' ':
                    old_left -= 1
                    new_left -= 1
                elif tag == '-':
                    old_left -= 1
                elif tag == '+':
                    new_left -= 1
                else:
                    break
                hunk.lines.append(body)
                i += 1
            if i < n and lines[i].startswith('\\'):
                hunk.lines.append(lines[i])
                i += 1
            cur.hunks.append(hunk)
        else:
            cur.header.append(line)
            i += 1
    return files


def read_text(path):
    if path == '-':
        return sys.stdin.read()
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def clip(s, width):
    s = s.replace('\t', ' ')
    return s if len(s) <= width else s[:max(width - 3, 1)] + '...'


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        prog='diff-hunk-stats.py',
        description='统计 diff 中每个 hunk 的增删行数并按改动幅度排序（详见文件头 docstring）。',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('diff_file', nargs='?', default='-',
                    help="输入 diff 文件；'-' 或省略表示 stdin")
    ap.add_argument('--sort', choices=['total', 'added', 'removed', 'file'],
                    default='total', help='排序依据（默认 total 降序）')
    ap.add_argument('--asc', action='store_true', help='改为升序')
    ap.add_argument('--top', type=int, default=0, metavar='N',
                    help='只显示改动最大的前 N 个 hunk（0=全部）')
    ap.add_argument('--json', action='store_true', help='输出 JSON 而非表格')
    args = ap.parse_args(argv)

    try:
        text = read_text(args.diff_file)
    except OSError as exc:
        sys.stderr.write('error: 读取输入失败: %s\n' % exc)
        return 2

    files = parse_unified_diff(text)
    if not files:
        sys.stderr.write('error: 输入中没有可识别的 unified diff\n')
        return 1

    rows = []
    for f in files:
        for h in f.hunks:
            added = sum(1 for l in h.lines if l.startswith('+'))
            removed = sum(1 for l in h.lines if l.startswith('-'))
            preview = ''
            for l in h.lines:
                if l[:1] in ('+', '-'):
                    preview = l[1:].strip()
                    break
            rows.append({'file': f.path, 'hunk': h.header, 'added': added,
                         'removed': removed, 'total': added + removed,
                         'preview': preview[:48]})

    if args.sort == 'file':
        rows.sort(key=lambda r: (r['file'], -r['total']))
    else:
        keymap = {
            'total': lambda r: (r['total'], r['added'], r['removed']),
            'added': lambda r: (r['added'], r['total']),
            'removed': lambda r: (r['removed'], r['total']),
        }
        rows.sort(key=keymap[args.sort], reverse=not args.asc)

    shown = rows[:args.top] if args.top > 0 else rows

    if args.json:
        sys.stdout.write(json.dumps(shown, ensure_ascii=False, indent=2) + '\n')
        return 0

    header = '%-30s %-28s %5s %5s %5s  %s' % ('FILE', 'HUNK', '+ADD', '-DEL',
                                              'TOTAL', 'PREVIEW')
    sys.stdout.write(header + '\n')
    sys.stdout.write('-' * len(header) + '\n')
    for r in shown:
        sys.stdout.write('%-30s %-28s %5d %5d %5d  %s\n' % (
            clip(r['file'], 28), clip(r['hunk'], 26),
            r['added'], r['removed'], r['total'], r['preview']))
    total_added = sum(r['added'] for r in rows)
    total_removed = sum(r['removed'] for r in rows)
    sys.stdout.write('-' * len(header) + '\n')
    note = ('，仅显示前 %d 条' % len(shown)) if args.top and len(rows) > len(shown) else ''
    sys.stdout.write('# %d 个 hunk / %d 个文件，共 +%d -%d 行（总计 %d）%s\n'
                     % (len(rows), len(set(r['file'] for r in rows)),
                        total_added, total_removed, total_added + total_removed, note))
    return 0


if __name__ == '__main__':
    sys.exit(main())
