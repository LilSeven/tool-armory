#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""超长行定位（long-line-finder）

用途：
    扫描文件或目录中长度超过指定列宽的行，输出文件、行号、长度
    与截断预览，按长度降序排列，便于快速定位"最长"的行。

示例命令：
    python -I long-line-finder.py src/ --max-len 120
    python -I long-line-finder.py . --ext .py,.js --top 30
    python -I long-line-finder.py README.md --max-len 80 --tabs 4

说明：长度按 Unicode 字符数计（中文按 1 个字符算）；给出 --tabs N
时先把制表符展开为 N 列空格再计算长度。预览默认截取前 60 字符
（Tab 显示为 \\t 转义）。二进制文件（前 8KB 含 \\0）自动跳过。
仅依赖 Python 标准库。
"""

import argparse
import os
import sys
import unicodedata

DEFAULT_EXCLUDES = {
    ".git", ".svn", ".hg", "__pycache__", "node_modules", "venv", ".venv",
    "dist", "build", ".idea", ".vscode", ".tox", ".mypy_cache",
}

DEFAULT_EXT_SPEC = (
    ".py,.pyw,.js,.mjs,.cjs,.ts,.tsx,.jsx,.java,.kt,.kts,.scala,.go,.rs,"
    ".c,.h,.cpp,.hpp,.cc,.cxx,.cs,.swift,.rb,.php,.pl,.lua,.dart,.groovy,"
    ".sh,.bash,.zsh,.ps1,.bat,.cmd,.sql,.html,.htm,.css,.scss,.less,.vue,"
    ".json,.yaml,.yml,.toml,.ini,.cfg,.conf,.xml,.md,.txt"
)


def _reconfigure_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _dw(s):
    """字符串显示宽度（全角字符记 2 列）。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
               for c in s)


def parse_exts(spec):
    """把 'a,b' 解析为扩展名集合；'*' 返回 None（不过滤）。"""
    spec = (spec or "").strip()
    if spec == "*":
        return None
    out = set()
    for e in spec.split(","):
        e = e.strip().lower()
        if e:
            out.add(e if e.startswith(".") else "." + e)
    return out


def iter_files(root, exts, excludes):
    """递归列出待扫描文件；exts=None 表示不限扩展名。"""
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in excludes and not d.startswith(".")
        )
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            if exts is not None and os.path.splitext(fn)[1].lower() not in exts:
                continue
            yield os.path.join(dirpath, fn)


def read_text(path):
    """读文本（utf-8，容错）；二进制文件返回 None。"""
    with open(path, "rb") as f:
        head = f.read(8192)
        if b"\x00" in head:
            return None
        f.seek(0)
        return f.read().decode("utf-8", errors="replace")


def _rel(path, root):
    if os.path.isdir(root):
        try:
            return os.path.relpath(path, root).replace(os.sep, "/")
        except ValueError:
            pass
    return path.replace(os.sep, "/")


def main(argv=None):
    _reconfigure_stdio()
    ap = argparse.ArgumentParser(
        prog="long-line-finder",
        description="扫描超过指定列宽的行，输出文件、行号、长度与截断预览。")
    ap.add_argument("path", help="要扫描的文件或目录")
    ap.add_argument("--max-len", type=int, default=120,
                    help="列宽阈值：行长度 > 该值才列出（默认 120）")
    ap.add_argument("--ext", default=DEFAULT_EXT_SPEC,
                    help="仅扫描这些扩展名（逗号分隔；'*'=全部文件）")
    ap.add_argument("--top", type=int, default=50,
                    help="按长度降序只显示前 N 条（0=全部，默认 50）")
    ap.add_argument("--preview", type=int, default=60,
                    help="预览截取的字符数（默认 60）")
    ap.add_argument("--tabs", type=int, default=0,
                    help="先把 Tab 展开为 N 列再计算长度（0=不展开）")
    ap.add_argument("--exclude", default="", help="额外排除的目录名（逗号分隔）")
    args = ap.parse_args(argv)

    if not os.path.exists(args.path):
        print("错误：路径不存在：%s" % args.path, file=sys.stderr)
        return 2

    excludes = set(DEFAULT_EXCLUDES)
    excludes |= {x.strip() for x in args.exclude.split(",") if x.strip()}
    exts = parse_exts(args.ext)

    hits = []
    per_file = {}
    n_files = n_bin = n_lines = 0
    for path in iter_files(args.path, exts, excludes):
        n_files += 1
        try:
            text = read_text(path)
        except OSError as exc:
            print("警告：无法读取 %s：%s" % (path, exc), file=sys.stderr)
            continue
        if text is None:
            n_bin += 1
            continue
        rel = _rel(path, args.path)
        cnt = 0
        for idx, line in enumerate(text.splitlines(), 1):
            n_lines += 1
            s = line.expandtabs(args.tabs) if args.tabs > 0 else line
            if len(s) > args.max_len:
                preview = line[:args.preview].replace("\t", "\\t")
                if len(line) > args.preview:
                    preview += "…"
                hits.append((len(s), rel, idx, preview))
                cnt += 1
        if cnt:
            per_file[rel] = cnt

    hits.sort(key=lambda h: (-h[0], h[1], h[2]))
    shown = hits if args.top <= 0 else hits[:args.top]

    print("== 超长行定位：%s（列宽 > %d）==" % (args.path, args.max_len))
    print()
    for length, rel, idx, preview in shown:
        print("%s:%d  长度=%d  预览: %s" % (rel, idx, length, preview))
    if per_file:
        print()
        print("按文件汇总（超长行数）：")
        for rel in sorted(per_file, key=lambda r: (-per_file[r], r)):
            print("  %s  %d 条" % (rel, per_file[rel]))
    print()
    tail = "共扫描 %d 个文件 / %d 行；超长行 %d 条，涉及 %d 个文件" % (
        n_files, n_lines, len(hits), len(per_file))
    if args.top > 0 and len(hits) > len(shown):
        tail += "，仅显示前 %d 条" % len(shown)
    if n_bin:
        tail += "；跳过二进制文件 %d 个" % n_bin
    print(tail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
