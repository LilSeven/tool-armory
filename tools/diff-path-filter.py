#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diff-path-filter.py —— diff 过滤工具：按路径通配或内容关键字保留/剔除相关 hunk。

用途
    读取 unified diff（stdin 或文件），先按路径通配符做"文件段"级过滤，
    再按内容关键字做 hunk 级过滤，最后把保留部分重新拼成 diff 输出。
    适合从大 patch 里只留关心的模块，或剔除带调试/临时代码的改动。

用法
    python diff-path-filter.py [输入diff] [选项]
    输入为 '-' 或省略时读 stdin；'-o' 缺省输出到 stdout。

选项
    --include GLOB      只保留路径匹配任一 GLOB 的文件段（可多次）
    --exclude GLOB      剔除路径匹配任一 GLOB 的文件段（可多次，优先于 include）
    --keep-keyword KW   只保留"改动行(+/-行)"含任一关键字的 hunk（可多次）
    --drop-keyword KW   剔除改动行含任一关键字的 hunk（可多次）
    --case-sensitive    关键字匹配区分大小写（默认不区分）

说明
    路径取自 +++/--- 行并去掉 a/、b/ 前缀，GLOB 为 fnmatch 风格（* 可跨目录）。
    关键字过滤把某文件段的 hunk 全部剔除时，该文件段整体不再输出。
    注意：输出沿用原行号，剔除 hunk 后不再保证是一个可直接 git apply 的
    完整补丁，主要供人工检阅或后续文本处理。

示例
    python diff-path-filter.py changes.patch --include 'src/*.py' -o src_only.patch
    git diff | python diff-path-filter.py --exclude 'tests/*' --drop-keyword TODO
    python diff-path-filter.py changes.patch --keep-keyword login

退出码
    0 成功；1 输入中没有可识别的 unified diff；2 读文件/参数错误。
"""
import argparse
import fnmatch
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
            i += 1          # 第一个文件段之前的游离行，忽略
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
                if tag == '\\':          # "\ No newline at end of file"
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
                    break                # 计数异常，提前结束该 hunk
                hunk.lines.append(body)
                i += 1
            if i < n and lines[i].startswith('\\'):
                hunk.lines.append(lines[i])
                i += 1
            cur.hunks.append(hunk)
        else:
            cur.header.append(line)      # diff --git / index / 模式行等
            i += 1
    return files


def read_text(path):
    if path == '-':
        return sys.stdin.read()
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def write_text(path, text):
    if path == '-':
        sys.stdout.write(text)
    else:
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)


def path_matches(path, globs):
    p = path.replace('\\', '/')
    return any(fnmatch.fnmatchcase(p, g.replace('\\', '/')) for g in globs)


def hunk_matches_keywords(hunk, keywords, case_sensitive):
    text = '\n'.join(l[1:] for l in hunk.lines if l[:1] in ('+', '-'))
    if not case_sensitive:
        text = text.lower()
        keywords = [k.lower() for k in keywords]
    return any(k in text for k in keywords)


def render(files):
    out = []
    for f in files:
        out.extend(f.header)
        for h in f.hunks:
            out.append(h.header)
            out.extend(h.lines)
    return ''.join(l + '\n' for l in out)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        prog='diff-path-filter.py',
        description='按路径通配或内容关键字过滤 unified diff（详细说明见文件头 docstring）。',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('diff_file', nargs='?', default='-',
                    help="输入 diff 文件；'-' 或省略表示 stdin")
    ap.add_argument('-o', '--output', default='-',
                    help="输出文件；'-'（默认）表示 stdout")
    ap.add_argument('--include', action='append', metavar='GLOB', default=[],
                    help='保留路径匹配的文件段，可多次')
    ap.add_argument('--exclude', action='append', metavar='GLOB', default=[],
                    help='剔除路径匹配的文件段，可多次')
    ap.add_argument('--keep-keyword', action='append', metavar='KW', default=[],
                    help='只保留改动行含关键字的 hunk，可多次')
    ap.add_argument('--drop-keyword', action='append', metavar='KW', default=[],
                    help='剔除改动行含关键字的 hunk，可多次')
    ap.add_argument('--case-sensitive', action='store_true',
                    help='关键字匹配区分大小写')
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

    keyword_active = bool(args.drop_keyword or args.keep_keyword)
    kept = []
    dropped_sections = 0
    dropped_hunks = 0
    for f in files:
        if args.include and not path_matches(f.path, args.include):
            dropped_sections += 1
            continue
        if args.exclude and path_matches(f.path, args.exclude):
            dropped_sections += 1
            continue
        before = len(f.hunks)
        if args.drop_keyword:
            f.hunks = [h for h in f.hunks
                       if not hunk_matches_keywords(h, args.drop_keyword,
                                                    args.case_sensitive)]
        if args.keep_keyword:
            f.hunks = [h for h in f.hunks
                       if hunk_matches_keywords(h, args.keep_keyword,
                                                args.case_sensitive)]
        dropped_hunks += before - len(f.hunks)
        if keyword_active and not f.hunks:
            dropped_sections += 1
            continue
        kept.append(f)

    result = render(kept)
    try:
        write_text(args.output, result)
    except OSError as exc:
        sys.stderr.write('error: 写输出失败: %s\n' % exc)
        return 2
    sys.stderr.write('info: 文件段保留 %d / 剔除 %d；hunk 剔除 %d\n'
                     % (len(kept), dropped_sections, dropped_hunks))
    return 0


if __name__ == '__main__':
    sys.exit(main())
