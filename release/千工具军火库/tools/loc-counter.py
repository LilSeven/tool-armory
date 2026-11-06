#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多语言行数统计器 (loc-counter)。

用途:
    递归统计目录下各文件的 代码行 / 注释行 / 空行, 并按语言汇总输出报表。
    语言按文件扩展名识别; 注释识别为启发式 (行注释前缀 + 块注释状态机),
    不解析字符串字面量, 结果为近似值。含 NUL 字节或无法按 UTF-8 解码的文件按二进制跳过;
    <文件名>.bak-时间戳 备份文件一律跳过。

示例命令:
    python loc-counter.py ./src
    python loc-counter.py ./src --ext .py,.js --files
    python loc-counter.py ./src --format csv
    python loc-counter.py ./src --sort files
"""

import argparse
import csv
import os
import sys
from pathlib import Path

DEFAULT_EXCLUDES = [".git", ".hg", ".svn", "__pycache__", "node_modules", ".idea", ".vscode"]

EXT_LANG = {
    ".py": "Python", ".pyw": "Python", ".pyi": "Python",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".scala": "Scala",
    ".swift": "Swift", ".go": "Go", ".rs": "Rust", ".dart": "Dart",
    ".c": "C", ".h": "C",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++", ".hh": "C++",
    ".cs": "C#", ".php": "PHP", ".rb": "Ruby", ".pl": "Perl", ".pm": "Perl",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell", ".ps1": "PowerShell",
    ".m": "Objective-C",
    ".html": "HTML", ".htm": "HTML", ".xhtml": "HTML", ".xml": "XML", ".svg": "XML",
    ".css": "CSS", ".scss": "SCSS", ".less": "Less", ".vue": "Vue",
    ".sql": "SQL", ".lua": "Lua", ".r": "R",
    ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML", ".ini": "INI", ".cfg": "INI", ".conf": "INI",
    ".json": "JSON", ".md": "Markdown", ".rst": "reST", ".txt": "Text",
}

LANG_STYLE = {
    "Python": "hash", "Shell": "hash", "Ruby": "hash", "YAML": "hash", "TOML": "hash",
    "R": "hash", "Perl": "hash", "INI": "hash", "PowerShell": "hash",
    "JavaScript": "slash", "TypeScript": "slash", "Java": "slash", "Kotlin": "slash",
    "Scala": "slash", "Swift": "slash", "Go": "slash", "Rust": "slash", "C": "slash",
    "C++": "slash", "C#": "slash", "PHP": "slash", "Objective-C": "slash",
    "SCSS": "slash", "Less": "slash", "Vue": "slash", "Dart": "slash",
    "CSS": "block", "HTML": "html", "XML": "html",
    "SQL": "sql", "Lua": "sql",
    "JSON": "none", "Markdown": "none", "reST": "none", "Text": "none",
}

STYLES = {
    "hash": ("#", None, None),
    "slash": ("//", "/*", "*/"),
    "block": (None, "/*", "*/"),
    "html": (None, "<!--", "-->"),
    "sql": ("--", "/*", "*/"),
    "none": (None, None, None),
}


def count_lines(text, style):
    """启发式统计: 返回 (代码行, 注释行, 空行)。块注释逐行计数, 不解析字符串字面量。"""
    line_m, b_open, b_close = STYLES[style]
    code = comment = blank = 0
    in_block = False
    for raw in text.splitlines():
        s = raw.strip()
        if in_block:
            comment += 1
            if b_close and b_close in s:
                in_block = False
            continue
        if not s:
            blank += 1
            continue
        if line_m and s.startswith(line_m):
            comment += 1
            continue
        if b_open and s.startswith(b_open):
            comment += 1
            if b_close and b_close not in s[len(b_open):]:
                in_block = True
            continue
        code += 1
    return code, comment, blank


def read_text_file(path):
    """二进制返回 None; 否则返回按 UTF-8 解码的文本 (容错)。"""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:8192]:
        return None
    return raw.decode("utf-8-sig", errors="replace")


def _parse_exts(s):
    exts = {e.strip().lower() for e in (s or "").split(",") if e.strip()}
    return exts or None


def iter_files(root, exts, excludes):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in excludes)
        for fn in sorted(filenames):
            if ".bak-" in fn:
                continue
            if exts is not None and os.path.splitext(fn)[1].lower() not in exts:
                continue
            yield Path(dirpath) / fn


def scan(root, exts, excludes):
    """返回 [(相对路径, 语言, 代码, 注释, 空行), ...]"""
    rows = []
    for path in iter_files(root, exts, excludes):
        text = read_text_file(path)
        if text is None:
            continue
        ext = path.suffix.lower()
        lang = EXT_LANG.get(ext, ext if ext else "(无扩展名)")
        code, comment, blank = count_lines(text, LANG_STYLE.get(lang, "none"))
        rows.append((path.relative_to(root).as_posix(), lang, code, comment, blank))
    return rows


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass
    ap = argparse.ArgumentParser(
        prog="loc-counter",
        description="递归统计目录下各文件的代码行/注释行/空行, 按语言汇总输出报表。")
    ap.add_argument("directory", help="要统计的目录")
    ap.add_argument("--ext", default="", metavar="EXTS",
                    help="仅统计这些扩展名, 逗号分隔 (如 .py,.js); 默认全部文件")
    ap.add_argument("--exclude-dirs", default=",".join(DEFAULT_EXCLUDES), metavar="DIRS",
                    help="要跳过的子目录名, 逗号分隔")
    ap.add_argument("--files", action="store_true", help="同时输出每个文件的明细")
    ap.add_argument("--format", choices=["table", "csv"], default="table", help="输出格式")
    ap.add_argument("--sort", choices=["code", "comment", "blank", "files", "total", "name"],
                    default="code", help="汇总排序依据 (默认按代码行降序)")
    args = ap.parse_args(argv)

    root = Path(args.directory)
    if not root.is_dir():
        print("目录不存在: %s" % root, file=sys.stderr)
        return 2
    exts = _parse_exts(args.ext)
    excludes = {d.strip() for d in args.exclude_dirs.split(",") if d.strip()}
    rows = scan(root, exts, excludes)
    if not rows:
        print("未找到可统计的文件")
        return 0

    agg = {}
    for _, lang, c, m, b in rows:
        d = agg.setdefault(lang, [0, 0, 0, 0])
        d[0] += 1
        d[1] += c
        d[2] += m
        d[3] += b
    keymap = {
        "code": lambda kv: (-kv[1][1], kv[0]),
        "comment": lambda kv: (-kv[1][2], kv[0]),
        "blank": lambda kv: (-kv[1][3], kv[0]),
        "files": lambda kv: (-kv[1][0], kv[0]),
        "total": lambda kv: (-(kv[1][1] + kv[1][2] + kv[1][3]), kv[0]),
        "name": lambda kv: kv[0],
    }
    items = sorted(agg.items(), key=keymap[args.sort])

    if args.format == "csv":
        w = csv.writer(sys.stdout, lineterminator="\n")
        if args.files:
            for rel, lang, c, m, b in rows:
                w.writerow(["file", rel, lang, c, m, b, c + m + b])
        for lang, (n, c, m, b) in items:
            w.writerow(["language", lang, n, c, m, b, c + m + b])
        return 0

    if args.files:
        w_name = max([len(r[0]) for r in rows] + [len("文件")])
        w_lang = max([len(r[1]) for r in rows] + [len("语言")])
        print("== 文件明细 ==")
        print("%-*s  %-*s  %5s  %5s  %5s  %6s" % (w_name, "文件", w_lang, "语言", "代码", "注释", "空行", "总计"))
        for rel, lang, c, m, b in sorted(rows):
            print("%-*s  %-*s  %5d  %5d  %5d  %6d" % (w_name, rel, w_lang, lang, c, m, b, c + m + b))
        print()
    print("== 按语言汇总 ==")
    w_lang = max([len(k) for k in agg] + [len("语言"), len("合计")])
    print("%-*s  %4s  %7s  %7s  %7s  %8s  %7s" % (w_lang, "语言", "文件", "代码行", "注释行", "空行", "总行", "注释率"))
    tot = [0, 0, 0, 0]
    for lang, (n, c, m, b) in items:
        ratio = (m / (c + m) * 100.0) if (c + m) else 0.0
        print("%-*s  %4d  %7d  %7d  %7d  %8d  %6.1f%%" % (w_lang, lang, n, c, m, b, c + m + b, ratio))
        tot[0] += n
        tot[1] += c
        tot[2] += m
        tot[3] += b
    ratio = (tot[2] / (tot[1] + tot[2]) * 100.0) if (tot[1] + tot[2]) else 0.0
    print("%-*s  %4d  %7d  %7d  %7d  %8d  %6.1f%%" % (w_lang, "合计", tot[0], tot[1], tot[2], tot[3], tot[1] + tot[2] + tot[3], ratio))
    return 0


if __name__ == "__main__":
    sys.exit(main())
