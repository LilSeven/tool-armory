#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diff-to-html.py —— diff 转 HTML：把 unified diff 渲染成带红绿高亮的 HTML 报告。

用途
    读取 unified diff，生成一个自包含的 HTML 报告文件：每个文件一个小节，
    逐行渲染——新增行绿底、删除行红底、上下文白底、hunk 头蓝底、
    文件头加粗，并带新旧行号列；支持亮/暗两种主题。纯标准库，无外部依赖。

用法
    python diff-to-html.py [输入diff] [-o 输出.html] [--title 标题] [--style light|dark]
    输入为 '-' 或省略时读 stdin；'-o' 缺省为 diff_report.html，'-' 表示 stdout。

示例
    python diff-to-html.py changes.patch -o report.html
    git diff | python diff-to-html.py -o review.html --title "登录模块评审" --style dark

退出码
    0 成功；1 输入中没有可识别的 unified diff；2 读文件/写文件/参数错误。
"""
import argparse
import html
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


CSS_LIGHT = """body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;margin:24px;background:#fafbfc;color:#24292f;}
h1{font-size:20px;margin:0 0 8px;}
h2.filehead{font-size:14px;margin:28px 0 8px;font-family:Consolas,Menlo,monospace;word-break:break-all;}
table{border-collapse:collapse;width:100%;font-family:Consolas,Menlo,"Courier New",monospace;font-size:12.5px;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.08);}
th,td{padding:2px 10px;vertical-align:top;white-space:pre-wrap;word-break:break-all;text-align:left;font-weight:normal;}
th{background:#eef1f4;border-bottom:1px solid #d7dde3;position:sticky;top:0;}
td.ln,th.ln{width:1%;min-width:3.5em;text-align:right;color:#9aa4ae;border-right:1px solid #e4e9ee;user-select:none;}
tr.add td{background:#e6ffec;}
tr.del td{background:#ffebe9;}
tr.hunk td{background:#ddf4ff;color:#4a6a8a;font-weight:bold;}
tr.meta td{color:#9aa4ae;font-style:italic;}
.counts{color:#9aa4ae;font-weight:normal;font-size:12px;}
.plus{color:#1a7f37;font-weight:bold;}
.minus{color:#cf222e;font-weight:bold;}
p.summary{color:#57606a;}
p.note{color:#9aa4ae;font-style:italic;}
p.footer{color:#9aa4ae;font-size:12px;margin-top:28px;}"""

CSS_DARK = """body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;margin:24px;background:#0d1117;color:#c9d1d9;}
h1{font-size:20px;margin:0 0 8px;}
h2.filehead{font-size:14px;margin:28px 0 8px;font-family:Consolas,Menlo,monospace;color:#e6edf3;word-break:break-all;}
table{border-collapse:collapse;width:100%;font-family:Consolas,Menlo,"Courier New",monospace;font-size:12.5px;background:#161b22;box-shadow:0 1px 3px rgba(0,0,0,.4);}
th,td{padding:2px 10px;vertical-align:top;white-space:pre-wrap;word-break:break-all;text-align:left;font-weight:normal;}
th{background:#1c2129;border-bottom:1px solid #2d333b;position:sticky;top:0;}
td.ln,th.ln{width:1%;min-width:3.5em;text-align:right;color:#6e7681;border-right:1px solid #2d333b;user-select:none;}
tr.add td{background:#1d3b26;}
tr.del td{background:#4b2427;}
tr.hunk td{background:#213b54;color:#9cc3e0;font-weight:bold;}
tr.meta td{color:#6e7681;font-style:italic;}
.counts{color:#6e7681;font-weight:normal;font-size:12px;}
.plus{color:#3fb950;font-weight:bold;}
.minus{color:#f85149;font-weight:bold;}
p.summary{color:#8b949e;}
p.note{color:#6e7681;font-style:italic;}
p.footer{color:#6e7681;font-size:12px;margin-top:28px;}"""

PAGE_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="summary">共 {n_files} 个文件，{n_hunks} 个 hunk，<span class="plus">+{added}</span> / <span class="minus">-{removed}</span> 行</p>
{body}
<p class="footer">由 diff-to-html.py（Python 标准库）生成</p>
</body>
</html>
"""


def hunk_rows_html(hunk):
    rows = []
    old_no, new_no = hunk.old_start, hunk.new_start
    for l in hunk.lines:
        tag = l[:1]
        if tag == '\\':
            rows.append('<tr class="meta"><td class="ln"></td>'
                        '<td class="ln"></td><td>%s</td></tr>' % html.escape(l))
            continue
        text = html.escape(l[1:] if tag in (' ', '-', '+') else l)
        if tag == ' ':
            rows.append('<tr class="ctx"><td class="ln">%d</td>'
                        '<td class="ln">%d</td><td>%s</td></tr>'
                        % (old_no, new_no, text))
            old_no += 1
            new_no += 1
        elif tag == '-':
            rows.append('<tr class="del"><td class="ln">%d</td>'
                        '<td class="ln"></td><td>%s</td></tr>' % (old_no, text))
            old_no += 1
        elif tag == '+':
            rows.append('<tr class="add"><td class="ln"></td>'
                        '<td class="ln">%d</td><td>%s</td></tr>' % (new_no, text))
            new_no += 1
        else:
            rows.append('<tr class="meta"><td class="ln"></td>'
                        '<td class="ln"></td><td>%s</td></tr>' % html.escape(l))
    return '\n'.join(rows)


def build_body(files):
    parts = []
    for f in files:
        fa = sum(1 for h in f.hunks for l in h.lines if l.startswith('+'))
        fr = sum(1 for h in f.hunks for l in h.lines if l.startswith('-'))
        head = '<h2 class="filehead">%s <span class="counts">+%d / -%d</span></h2>' \
               % (html.escape(f.path or '(unknown)'), fa, fr)
        chunks = []
        for h in f.hunks:
            chunks.append('<tr class="hunk"><td class="ln"></td>'
                          '<td class="ln"></td><td>%s</td></tr>' % html.escape(h.header))
            chunks.append(hunk_rows_html(h))
        if chunks:
            table = ('<table>\n<tr class="tablehead"><th class="ln">旧</th>'
                     '<th class="ln">新</th><th>内容</th></tr>\n%s\n</table>'
                     % '\n'.join(chunks))
            parts.append(head + '\n' + table)
        else:
            parts.append(head + '\n<p class="note">（该文件段没有 hunk：'
                                '可能是二进制文件或纯元数据改动）</p>')
    return '\n'.join(parts)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        prog='diff-to-html.py',
        description='把 unified diff 渲染成带红绿高亮的 HTML 报告（详见文件头 docstring）。',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('diff_file', nargs='?', default='-',
                    help="输入 diff 文件；'-' 或省略表示 stdin")
    ap.add_argument('-o', '--output', default='diff_report.html',
                    help="输出 HTML 文件（默认 diff_report.html，'-' 表示 stdout）")
    ap.add_argument('--title', default='Diff 报告', help='报告标题')
    ap.add_argument('--style', choices=['light', 'dark'], default='light',
                    help='配色主题（默认 light）')
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

    n_hunks = sum(len(f.hunks) for f in files)
    added = sum(1 for f in files for h in f.hunks
                for l in h.lines if l.startswith('+'))
    removed = sum(1 for f in files for h in f.hunks
                  for l in h.lines if l.startswith('-'))

    page = PAGE_TMPL.format(
        title=html.escape(args.title),
        css=CSS_LIGHT if args.style == 'light' else CSS_DARK,
        n_files=len(files), n_hunks=n_hunks,
        added=added, removed=removed,
        body=build_body(files))

    try:
        if args.output == '-':
            sys.stdout.write(page)
            out_desc = 'stdout'
        else:
            with open(args.output, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(page)
            out_desc = '%s（%d 字节）' % (args.output, len(page.encode('utf-8')))
    except OSError as exc:
        sys.stderr.write('error: 写输出失败: %s\n' % exc)
        return 2
    sys.stderr.write('info: 已生成 %s：%d 个文件，%d 个 hunk，+%d/-%d 行\n'
                     % (out_desc, len(files), n_hunks, added, removed))
    return 0


if __name__ == '__main__':
    sys.exit(main())
