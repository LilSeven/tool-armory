#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch-apply-check.py —— 补丁预检：校验 patch 的上下文行能否在目标文件中找到。

用途
    对 unified patch 的每个 hunk，取出其"旧侧"行（上下文行 + 被删除行），
    在目标文件声明位置附近（允许 ±N 行漂移）查找完全一致的连续片段，
    逐 hunk 报告"精确匹配 / 行号漂移后匹配 / 找不到"，并给出能否干净应用的
    总结。相当于 `git apply --check` 的简化独立版：只校验、不修改任何文件。

用法
    python patch-apply-check.py PATCH TARGET [--max-offset N] [--ignore-whitespace] [-q]

    PATCH    unified diff/patch 文件，'-' 表示 stdin
    TARGET   目标文件；或目标目录（按 patch 内去掉 a/、b/ 前缀的旧路径定位文件）
    新建文件段（--- /dev/null）只检查目标是否已存在；无 hunk 的段（二进制等）跳过。

示例
    python patch-apply-check.py fix.patch src/app.py
    python patch-apply-check.py fix.patch ./src --ignore-whitespace
    cat fix.patch | python patch-apply-check.py - src/app.py

退出码
    0 所有 hunk 均可匹配（可干净应用）；1 有 hunk 匹配失败（无法干净应用）；
    2 patch 无法解析 / 目标不存在等硬错误。
"""
import argparse
import os
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


def read_lines(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read().splitlines()


def hunk_old_lines(hunk):
    """hunk 的旧侧行：上下文行 + 被删除行（不含 '\\ No newline' 标记行）。"""
    return [l[1:] for l in hunk.lines if l[:1] in (' ', '-')]


def match_hunk(target_lines, old_lines, start_idx, max_offset, ignore_ws):
    """在 target_lines 中从 start_idx(0 基) ± max_offset 范围查找 old_lines。
    返回 (命中下标, 状态)；状态 ∈ CLEAN / OFFSET±k / EMPTY / MISMATCH。"""
    if not old_lines:
        return max(start_idx, 0), 'EMPTY'
    if ignore_ws:
        olds = [' '.join(x.split()) for x in old_lines]
    else:
        olds = list(old_lines)
    n = len(target_lines)
    for off in range(0, max_offset + 1):
        candidates = (start_idx,) if off == 0 else (start_idx + off, start_idx - off)
        for pos in candidates:
            if 0 <= pos and pos + len(olds) <= n:
                seg = target_lines[pos:pos + len(olds)]
                if ignore_ws:
                    seg = [' '.join(x.split()) for x in seg]
                if seg == olds:
                    if off == 0:
                        return pos, 'CLEAN'
                    return pos, 'OFFSET%+d' % (pos - start_idx)
    return -1, 'MISMATCH'


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        prog='patch-apply-check.py',
        description='校验 patch 的上下文行能否在目标文件中找到（详见文件头 docstring）。',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('patch', help="patch 文件；'-' 表示 stdin")
    ap.add_argument('target', help='目标文件或目标目录')
    ap.add_argument('--max-offset', type=int, default=100, metavar='N',
                    help='允许的行号漂移上限（默认 100 行）')
    ap.add_argument('--ignore-whitespace', action='store_true',
                    help='比较时把连续空白折叠为单个空格')
    ap.add_argument('-q', '--quiet', action='store_true', help='只输出汇总')
    args = ap.parse_args(argv)

    try:
        text = read_text(args.patch)
    except OSError as exc:
        sys.stderr.write('error: 读取 patch 失败: %s\n' % exc)
        return 2
    files = parse_unified_diff(text)
    if not files:
        sys.stderr.write('error: patch 中没有可识别的 unified diff\n')
        return 2

    if os.path.isdir(args.target):
        target_is_dir = True
    elif os.path.isfile(args.target):
        target_is_dir = False
        if len(files) > 1:
            sys.stderr.write('error: patch 含 %d 个文件段，TARGET 请给目录\n'
                             % len(files))
            return 2
    else:
        sys.stderr.write('error: 目标不存在: %s\n' % args.target)
        return 2

    out_lines = []
    total = matched = 0
    for f in files:
        if f.old_path == '/dev/null':            # 新建文件
            rel = f.new_path
        else:
            rel = f.old_path or f.new_path
        if target_is_dir:
            tpath = os.path.join(args.target, rel.replace('/', os.sep))
        else:
            tpath = args.target

        if not f.hunks:                          # 二进制或纯元数据段
            out_lines.append('[SKIP] %-16s 无 hunk（二进制或纯元数据段），跳过' % rel)
            continue

        if f.old_path == '/dev/null':
            exists = os.path.isfile(tpath)
            for idx, h in enumerate(f.hunks, 1):
                total += 1
                if exists:
                    out_lines.append('[FAIL] %-16s hunk %d/%d  %s  新建文件但目标已存在: %s'
                                     % (f.new_path, idx, len(f.hunks), h.header, tpath))
                else:
                    matched += 1
                    if not args.quiet:
                        out_lines.append('[OK]   %-16s hunk %d/%d  %s  新建文件，无需校验内容'
                                         % (f.new_path, idx, len(f.hunks), h.header))
            continue

        if not os.path.isfile(tpath):
            for idx, h in enumerate(f.hunks, 1):
                total += 1
                out_lines.append('[FAIL] %-16s hunk %d/%d  %s  目标文件不存在: %s'
                                 % (rel, idx, len(f.hunks), h.header, tpath))
            continue

        tlines = read_lines(tpath)
        for idx, h in enumerate(f.hunks, 1):
            total += 1
            olds = hunk_old_lines(h)
            pos, status = match_hunk(tlines, olds, h.old_start - 1,
                                     args.max_offset, args.ignore_whitespace)
            if status == 'CLEAN' or status.startswith('OFFSET') or status == 'EMPTY':
                matched += 1
            if status == 'CLEAN':
                detail = '精确匹配（目标第 %d 行）' % (pos + 1)
            elif status.startswith('OFFSET'):
                detail = '行号漂移 %s 后匹配（目标第 %d 行）' % (status[6:], pos + 1)
            elif status == 'EMPTY':
                detail = 'hunk 无旧侧行（纯新增），无需校验'
            else:
                first = olds[0].strip() if olds else ''
                if len(first) > 40:
                    first = first[:40] + '...'
                detail = '±%d 行内找不到旧侧 %d 行内容（首行: %r）' % (
                    args.max_offset, len(olds), first)
            if not args.quiet:
                out_lines.append('[%s] %-16s hunk %d/%d  %s  %s'
                                 % ('OK' if status != 'MISMATCH' else 'FAIL',
                                    rel, idx, len(f.hunks), h.header, detail))

    for line in out_lines:
        sys.stdout.write(line + '\n')
    if total == 0:
        sys.stdout.write('没有可校验的 hunk\n')
        return 0
    sys.stdout.write('汇总: %d/%d 个 hunk 可匹配 —— %s\n'
                     % (matched, total,
                        'patch 可以干净应用' if matched == total
                        else 'patch 无法干净应用'))
    return 0 if matched == total else 1


if __name__ == '__main__':
    sys.exit(main())
