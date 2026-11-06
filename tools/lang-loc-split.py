#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""语言占比分析 (lang-loc-split)。

用途:
    递归按文件扩展名分组统计行数, 计算各语言占比, 用百分比条展示。
    占比默认按总行数, 可用 --by code 改为按代码行 (非空行且非注释行)。
    注释识别为启发式 (行注释前缀 + 块注释状态机), 不解析字符串字面量;
    含 NUL 字节的文件按二进制跳过; .bak-时间戳 备份文件一律跳过。

示例命令:
    python lang-loc-split.py ./src
    python lang-loc-split.py ./src --top 5 --width 40
    python lang-loc-split.py ./src --by code
    python lang-loc-split.py ./src --format csv
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


def bar(pct, width):
    n = int(round(pct / 100.0 * width))
    if 0 < pct < 100 and n < 1:
        n = 1
    return "#" * n if width <= 0 else "█" * n


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
        prog="lang-loc-split",
        description="按文件扩展名分组统计行数并计算各语言占比, 用百分比条展示。")
    ap.add_argument("directory", help="要分析的目录")
    ap.add_argument("--ext", default="", metavar="EXTS", help="仅统计这些扩展名, 逗号分隔; 默认全部文件")
    ap.add_argument("--exclude-dirs", default=",".join(DEFAULT_EXCLUDES), metavar="DIRS",
                    help="要跳过的子目录名, 逗号分隔")
    ap.add_argument("--by", choices=["lines", "code"], default="lines",
                    help="占比按 总行数 或 代码行 (默认 lines)")
    ap.add_argument("--top", type=int, default=0, metavar="N", help="只显示占比最高的前 N 项 (0=全部)")
    ap.add_argument("--width", type=int, default=30, metavar="N", help="百分比条宽度字符数 (默认 30)")
    ap.add_argument("--format", choices=["table", "csv"], default="table", help="输出格式")
    args = ap.parse_args(argv)

    root = Path(args.directory)
    if not root.is_dir():
        print("目录不存在: %s" % root, file=sys.stderr)
        return 2
    exts = _parse_exts(args.ext)
    excludes = {d.strip() for d in args.exclude_dirs.split(",") if d.strip()}

    agg = {}  # ext -> [files, lines, code]
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
            d = agg.setdefault(ext, [0, 0, 0])
            d[0] += 1
            d[1] += code + comment + blank
            d[2] += code

    if not agg:
        print("未找到可统计的文件")
        return 0

    metric_idx = 1 if args.by == "lines" else 2
    grand = sum(d[metric_idx] for d in agg.values())
    items = sorted(agg.items(), key=lambda kv: (-kv[1][metric_idx], kv[0]))
    if args.top > 0:
        items = items[: args.top]

    if args.format == "csv":
        w = csv.writer(sys.stdout, lineterminator="\n")
        w.writerow(["ext", "language", "files", "lines", "percent"])
        for ext, (n, lines, code) in items:
            metric = lines if args.by == "lines" else code
            pct = (metric / grand * 100.0) if grand else 0.0
            w.writerow([ext, EXT_LANG.get(ext, ext if ext else "(无扩展名)"), n, metric, "%.1f" % pct])
        return 0

    label = "总行数" if args.by == "lines" else "代码行"
    w_name = max([len("%s %s" % (EXT_LANG.get(e, e), e)) for e, _ in items] + [len("语言/扩展名")])
    print("== 语言占比 (按%s, 共 %s) ==" % (label, format(grand, ",")))
    print("%-*s  %5s  %9s  %7s  百分比条" % (w_name, "语言/扩展名", "文件", label, "占比"))
    for ext, (n, lines, code) in items:
        metric = lines if args.by == "lines" else code
        pct = (metric / grand * 100.0) if grand else 0.0
        name = "%s %s" % (EXT_LANG.get(ext, ext if ext else "(无扩展名)"), ext)
        print("%-*s  %5d  %9s  %6.1f%%  %s" % (w_name, name, n, format(metric, ","), pct, bar(pct, args.width)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
