#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch-summary.py —— 补丁意图摘要：为 diff 中每处改动标注所在函数/区域。

用途
    解析 unified diff，对每个 hunk 在其旧侧行（上下文行 + 被删除行）中
    自下而上寻找最近的函数定义行（Python 的 def/class，或 C/JS/Java 风格
    的函数头），标注该 hunk 大致落在哪个函数、def 的旧行号；同时参考
    git 风格 @@ 行尾的函数提示，并识别 hunk 中新增的函数定义。
    一个 hunk 跨多个区域时，以其中最后一处非空行改动为准。
    纯启发式，判断不了时标注 top-level。

用法
    python patch-summary.py [输入diff] [--lang auto|python|generic] [--json]
    输入为 '-' 或省略时读 stdin。

示例
    python patch-summary.py changes.patch
    git diff | python patch-summary.py --lang python
    python patch-summary.py changes.patch --json

退出码
    0 成功；1 输入中没有可识别的 unified diff；2 读文件/参数错误。
"""
import argparse
import json
import re
import sys

HUNK_HEADER_RE = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$')

PY_DEF_RE = re.compile(r'^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)')
PY_CLASS_RE = re.compile(r'^\s*class\s+([A-Za-z_]\w*)')
JS_FUNC_RE = re.compile(
    r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_]\w*)')
MODIFIER_RE = re.compile(
    r'^\s*(?:public|private|protected|internal|static|final|abstract|'
    r'override|virtual|synchronized|async)\b')
GENERIC_COL0_RE = re.compile(r'^[\w \t\*&:<>]*?\b([A-Za-z_]\w*)\s*\(')
NOT_FUNC_KEYWORDS = {
    'if', 'else', 'elif', 'for', 'while', 'switch', 'case', 'default', 'do',
    'return', 'goto', 'break', 'continue', 'sizeof', 'typedef', 'new',
    'delete', 'catch', 'throw', 'try', 'except', 'finally', 'raise', 'with',
    'assert', 'yield', 'pass', 'lambda', 'print', 'and', 'or', 'not', 'in', 'is',
}


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


def indent_of(text):
    return len(text) - len(text.lstrip(' '))


def generic_func_name(text):
    """从一行 C/JS/Java 风格文本中启发式地提取函数名，失败返回 None。"""
    core = text.strip()
    if not core or core.endswith(';') or core.startswith(('#', '//', '/*', '*', '"', "'")):
        return None
    m = JS_FUNC_RE.match(core)
    if m:
        return m.group(1)
    if MODIFIER_RE.match(core):
        m2 = re.search(r'([A-Za-z_]\w*)\s*\(', core)
        if m2:
            return m2.group(1)
    if text[:1] not in (' ', '\t'):            # C 风格定义通常顶格
        m3 = GENERIC_COL0_RE.match(core)
        if m3 and m3.group(1) not in NOT_FUNC_KEYWORDS:
            return m3.group(1)
    return None


def def_name_in(text, lang):
    if lang == 'python':
        m = PY_DEF_RE.match(text)
        return m.group(1) if m else None
    return generic_func_name(text)


def section_func_name(section, lang):
    """从 git 风格 @@ 行尾的函数提示文本里取函数名。"""
    if not section:
        return None
    s = section.strip()
    if lang == 'python':
        m = PY_DEF_RE.match(s)
        if m:
            return m.group(1)
        m = PY_CLASS_RE.match(s)
        if m:
            return m.group(1)
        return None
    return generic_func_name(s)


def find_region_python(cands, change_indent):
    """cands: [(旧行号, 文本)]（改动行上方的旧侧内容）；返回 (区域名, def行号)。"""
    func = func_ln = func_ind = None
    cls = None
    for ln, text in reversed(cands):
        if func is None:
            m = PY_DEF_RE.match(text)
            if m and (change_indent is None or indent_of(text) < change_indent):
                func, func_ln, func_ind = m.group(1), ln, indent_of(text)
                continue
        if cls is None:
            m = PY_CLASS_RE.match(text)
            if m and ((func is not None and indent_of(text) < func_ind)
                      or (func is None and (change_indent is None
                                            or indent_of(text) < change_indent))):
                cls = m.group(1)
    if func and cls:
        return '%s.%s' % (cls, func), func_ln
    if func:
        return func, func_ln
    if cls:
        return '%s (类体)' % cls, None
    return None, None


def find_region_generic(cands):
    for ln, text in reversed(cands):
        if text.strip():
            name = generic_func_name(text)
            if name:
                return name, ln
    return None, None


def detect_lang(files):
    for f in files:
        for h in f.hunks:
            for l in h.lines:
                if l[:1] in (' ', '-', '+'):
                    body = l[1:]
                    if PY_DEF_RE.match(body) or PY_CLASS_RE.match(body):
                        return 'python'
    return 'generic'


def analyze_hunk(hunk, lang):
    """返回 (区域名, def旧行号, 增行, 删行, 新增函数列表, 来源)。"""
    old_no = hunk.old_start
    old_side = []               # (旧行号, 文本)：' ' 与 '-' 行
    last_pos = None             # 最后一处非空行改动的旧侧位置
    last_indent = None          # 其缩进
    added_defs = []
    added = removed = 0
    for l in hunk.lines:
        tag = l[:1]
        if tag == '\\':
            continue
        body = l[1:]
        if tag == '+':
            added += 1
            if body.strip():
                last_pos = old_no
                last_indent = indent_of(body)
            name = def_name_in(body, lang)
            if name:
                added_defs.append(name)
        elif tag == '-':
            removed += 1
            old_side.append((old_no, body))
            if body.strip():
                last_pos = old_no
                last_indent = indent_of(body)
            old_no += 1
        else:
            old_side.append((old_no, body))
            old_no += 1

    cands = [(ln, t) for (ln, t) in old_side
             if last_pos is None or ln < last_pos]
    source = 'context'
    if lang == 'python':
        region, def_ln = find_region_python(cands, last_indent)
    else:
        region, def_ln = find_region_generic(cands)

    if region is None and hunk.section:
        name = section_func_name(hunk.section, lang)
        if name and (lang != 'python' or last_indent is None or last_indent > 0):
            region, def_ln, source = name, None, 'hunk-header'

    if region is None:
        region, def_ln, source = 'top-level', None, 'top-level'
    return region, def_ln, added, removed, added_defs, source


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        prog='patch-summary.py',
        description='为 diff 中每处改动标注所在函数/区域（详见文件头 docstring）。',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('diff_file', nargs='?', default='-',
                    help="输入 diff 文件；'-' 或省略表示 stdin")
    ap.add_argument('--lang', choices=['auto', 'python', 'generic'], default='auto',
                    help='函数定义识别风格（默认 auto 自动检测）')
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

    lang = detect_lang(files) if args.lang == 'auto' else args.lang

    rows = []
    for f in files:
        for h in f.hunks:
            region, def_ln, added, removed, added_defs, source = \
                analyze_hunk(h, lang)
            note = ''
            if added_defs:
                names = ', '.join(added_defs[:3])
                if len(added_defs) > 3:
                    names += ', ...'
                note = '新增定义: ' + names
            rows.append({'file': f.path, 'hunk': h.header, 'region': region,
                         'def_line': def_ln, 'added': added, 'removed': removed,
                         'note': note, 'source': source, 'lang': lang})

    if args.json:
        sys.stdout.write(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
        return 0

    header = '%-18s %-30s %-18s %-8s %-8s %s' % (
        'FILE', 'HUNK', 'REGION', 'DEF@OLD', '+/-', 'NOTE')
    sys.stdout.write(header + '\n')
    sys.stdout.write('-' * len(header) + '\n')
    for r in rows:
        hunk_disp = r['hunk'].replace('\t', ' ')
        sys.stdout.write('%-18s %-30s %-18s %-8s %-8s %s\n' % (
            (r['file'][:15] + '...') if len(r['file']) > 18 else r['file'],
            (hunk_disp[:27] + '...') if len(hunk_disp) > 30 else hunk_disp,
            r['region'][:16],
            str(r['def_line']) if r['def_line'] is not None else '-',
            '+%d/-%d' % (r['added'], r['removed']),
            r['note']))
    in_func = sum(1 for r in rows if r['region'] != 'top-level')
    sys.stdout.write('-' * len(header) + '\n')
    sys.stdout.write('# %d 个 hunk（%s 风格）：%d 个标注到函数/类，%d 个 top-level\n'
                     % (len(rows), lang, in_func, len(rows) - in_func))
    return 0


if __name__ == '__main__':
    sys.exit(main())
