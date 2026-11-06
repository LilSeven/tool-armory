#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""注释率预警 (comment-ratio)。

用途:
    递归统计每个文件的注释率 (注释行 / (代码行 + 注释行)),
    列出低于阈值的文件作为低注释预警清单。
    注释识别为启发式 (行注释前缀 + 块注释状态机), 不解析字符串字面量;
    含 NUL 字节的文件按二进制跳过; .bak-时间戳 备份文件一律跳过。
    默认退出码 0; 加 --fail 时若存在预警文件则退出码为 1 (可用于 CI 门禁)。

示例命令:
    python comment-ratio.py ./src --threshold 0.15
    python comment-ratio.py ./src --threshold 20% --all
    python comment-ratio.py ./src --ext .py,.js --fail
"""

import argparse
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


def count_code_comment_blank(text, style):
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
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:8192]:
        return None
    return raw.decode("utf-8-sig", errors="replace")


def parse_threshold(s):
    """支持 0.15 (小数) 或 15% (百分数), 返回 0-1 之间的小数。"""
    t = (s or "").strip()
    if t.endswith("%"):
        v = float(t[:-1]) / 100.0
    else:
        v = float(t)
    if not 0.0 <= v <= 1.0:
        raise ValueError("阈值需在 0-1 之间或写成 N%% 形式: %r" % s)
    return v


def _parse_exts(s):
    exts = {e.strip().lower() for e in (s or "").split(",") if e.strip()}
    return exts or None


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass
    ap = argparse.ArgumentParser(
        prog="comment-ratio",
        description="统计每个文件的注释率 (注释行/(代码行+注释行)), 列出低于阈值的文件作为预警清单。")
    ap.add_argument("directory", help="要检查的目录")
    ap.add_argument("--threshold", default="0.10", metavar="T",
                    help="注释率阈值, 支持 0.15 或 15%% 两种写法 (默认 0.10)")
    ap.add_argument("--ext", default="", metavar="EXTS", help="仅检查这些扩展名, 逗号分隔; 默认全部文件")
    ap.add_argument("--exclude-dirs", default=",".join(DEFAULT_EXCLUDES), metavar="DIRS",
                    help="要跳过的子目录名, 逗号分隔")
    ap.add_argument("--all", action="store_true", help="同时列出达标文件 (按注释率升序)")
    ap.add_argument("--fail", action="store_true", help="存在预警文件时退出码为 1 (CI 门禁用)")
    args = ap.parse_args(argv)

    try:
        threshold = parse_threshold(args.threshold)
    except ValueError as e:
        print("参数错误: %s" % e, file=sys.stderr)
        return 2
    root = Path(args.directory)
    if not root.is_dir():
        print("目录不存在: %s" % root, file=sys.stderr)
        return 2
    exts = _parse_exts(args.ext)
    excludes = {d.strip() for d in args.exclude_dirs.split(",") if d.strip()}

    stats = []  # (relpath, code, comment, blank, ratio)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in excludes)
        for fn in sorted(filenames):
            if ".bak-" in fn:
                continue
            ext = os.path.splitext(fn)[1].lower()
            if exts is not None and ext not in exts:
                continue
            path = Path(dirpath) / fn
            text = read_text_file(path)
            if text is None:
                continue
            lang = EXT_LANG.get(ext, ext if ext else "(无扩展名)")
            code, comment, blank = count_code_comment_blank(
                text, LANG_STYLE.get(lang, "none"))
            denom = code + comment
            ratio = (comment / denom) if denom else 0.0
            stats.append((path.relative_to(root).as_posix(), code, comment, blank, ratio))

    if not stats:
        print("未找到可检查的文件")
        return 0

    warn = [s for s in stats if s[4] < threshold]
    ok = [s for s in stats if s[4] >= threshold]
    warn.sort(key=lambda s: (s[4], s[0]))
    ok.sort(key=lambda s: (s[4], s[0]))

    print("注释率阈值: %.1f%% | 注释率 = 注释行 / (代码行 + 注释行)" % (threshold * 100.0))
    if warn:
        print()
        print("低于阈值 %d 个:" % len(warn))
        for rel, code, comment, _blank, ratio in warn:
            print("  [预警] %5.1f%%  %-40s  代码 %4d  注释 %3d" % (ratio * 100.0, rel, code, comment))
    if args.all and ok:
        print()
        print("达标 %d 个 (按注释率升序):" % len(ok))
        for rel, code, comment, _blank, ratio in ok:
            print("  [达标] %5.1f%%  %-40s  代码 %4d  注释 %3d" % (ratio * 100.0, rel, code, comment))
    print()
    print("汇总: 扫描 %d 个文件 | 预警 %d | 达标 %d" % (len(stats), len(warn), len(ok)))
    if args.fail and warn:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
