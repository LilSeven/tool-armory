#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""脚本类型普查 (script-type-census) —— 通过 shebang 与扩展名统计目录内脚本的数量分布。

递归遍历目录(默认当前目录)中的非二进制文件:
  1. 按扩展名归类计数;
  2. 读文件头部，若以 "#!" 开头则解析解释器(支持 "#!/usr/bin/env xxx" 形式)并计数。
输出两张分布表(带条形示意)，用于快速摸清一个仓库里脚本的种类构成。
自动跳过二进制文件与常见无关目录(.git、node_modules 等)。

示例:
  python script-type-census.py                    # 普查当前目录
  python script-type-census.py src/ lib/          # 普查多个目录
  python script-type-census.py . --top 10         # 每张表只显示前 10 名
  python script-type-census.py . --by shebang     # 只看 shebang 分布
  python script-type-census.py . --scripts-only   # 只统计脚本(有 shebang 或已知脚本扩展名)
  python script-type-census.py . --hidden         # 包含 . 开头的隐藏目录

退出码: 0 = 正常; 1 = 参数或路径错误。
仅用 Python 标准库，单文件。
"""

import argparse
import os
import sys

DEFAULT_IGNORE_DIRS = {
    '.git', '.hg', '.svn', '__pycache__', 'node_modules', '.venv', 'venv',
    '.tox', '.mypy_cache', '.pytest_cache', '.idea', '.vscode',
}
NO_EXT = '(无扩展名)'
NO_SHEBANG = '(无 shebang)'

KNOWN_SCRIPT_EXTS = {
    '.py', '.pyw', '.sh', '.bash', '.zsh', '.ksh', '.fish', '.js', '.mjs',
    '.cjs', '.ts', '.tsx', '.jsx', '.rb', '.pl', '.pm', '.php', '.lua',
    '.tcl', '.ps1', '.psm1', '.bat', '.cmd', '.vbs', '.awk', '.sed', '.r',
    '.jl', '.sql',
}


def parse_shebang(head):
    """从文件头部字节解析 shebang，返回解释器名(如 python3/bash)；无则 None。"""
    if not head.startswith(b'#!'):
        return None
    line = head.split(b'\n', 1)[0].decode('utf-8', 'replace').strip('\r\t ')
    toks = line[2:].strip().split()
    if not toks:
        return None
    if os.path.basename(toks[0]) == 'env':
        rest = toks[1:]
        idx = 0
        while idx < len(rest) and rest[idx].startswith('-'):
            idx += 1
        if idx >= len(rest):
            return None
        toks = rest[idx:]
    interp = os.path.basename(toks[0]).strip('"\'')
    return interp or None


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


def census(paths, scripts_only, hidden, follow):
    """返回 (ext分布, shebang分布, 文件数, 跳过二进制数, 读取失败数)。"""
    ext_counter = {}
    she_counter = {}
    total = binary = unreadable = 0
    for path in iter_files(paths, hidden, follow):
        try:
            with open(path, 'rb') as f:
                head = f.read(8192)
        except OSError:
            unreadable += 1
            continue
        if b'\x00' in head:
            binary += 1
            continue
        she = parse_shebang(head)
        ext = os.path.splitext(path)[1].lower() or NO_EXT
        if scripts_only and she is None and ext not in KNOWN_SCRIPT_EXTS:
            continue
        total += 1
        ext_counter[ext] = ext_counter.get(ext, 0) + 1
        she_key = she if she else NO_SHEBANG
        she_counter[she_key] = she_counter.get(she_key, 0) + 1
    return ext_counter, she_counter, total, binary, unreadable


def print_table(title, counter, top):
    print('== %s ==' % title)
    if not counter:
        print('  (无)')
        return 0
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    hidden_count = 0
    if top > 0 and len(items) > top:
        hidden_count = len(items) - top
        items = items[:top]
    peak = max(c for _n, c in items) or 1
    width = max(len(n) for n, _c in items)
    for name, count in items:
        bar = '#' * max(1, round(count / peak * 20))
        print('  %-*s %5d  %s' % (width, name, count, bar))
    if hidden_count:
        print('  (其余 %d 项省略，可加大 --top 查看)' % hidden_count)
    return len(items)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        prog='script-type-census',
        description='通过 shebang 与扩展名统计目录内各类脚本的数量分布。')
    parser.add_argument('paths', nargs='*', default=['.'],
                        help='要普查的文件或目录，默认当前目录')
    parser.add_argument('--by', choices=('both', 'ext', 'shebang'), default='both',
                        help='展示维度(默认 both 两张表都出)')
    parser.add_argument('--top', type=int, default=0, metavar='N',
                        help='每张表只显示前 N 名(默认 0=全部)')
    parser.add_argument('--scripts-only', action='store_true',
                        help='只统计脚本(有 shebang 或已知脚本扩展名的文件)')
    parser.add_argument('--hidden', action='store_true',
                        help='同时进入 . 开头的隐藏目录(常见无关目录仍会跳过)')
    parser.add_argument('--follow-symlinks', action='store_true',
                        help='跟随目录符号链接')
    args = parser.parse_args(argv)

    missing = [p for p in args.paths if not os.path.exists(p)]
    if missing:
        print('错误: 路径不存在: %s' % ', '.join(missing), file=sys.stderr)
        return 1

    ext_counter, she_counter, total, binary, unreadable = census(
        args.paths, args.scripts_only, args.hidden, args.follow_symlinks)

    if args.by in ('both', 'ext'):
        print_table('按扩展名', ext_counter, args.top)
        print()
    if args.by in ('both', 'shebang'):
        print_table('按 shebang 解释器', she_counter, args.top)
        print()
    print('-- 普查完成: 共 %d 个文件%s(跳过二进制 %d, 读取失败 %d) --'
          % (total, '(仅脚本)' if args.scripts_only else '', binary, unreadable))
    return 0


if __name__ == '__main__':
    sys.exit(main())
