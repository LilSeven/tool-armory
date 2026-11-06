#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""缩进风格体检（indent-style-report）

用途：
    递归扫描目录（或单文件），统计每行行首缩进使用 Tab 还是空格，
    输出整体比例、文件风格归类，以及混用文件清单（同一文件既用
    Tab 又用空格缩进，或行首 Tab+空格混用）。

统计口径：
    * 只统计"非空白行"的行首连续空白；顶格（无缩进）行不计入比例；
    * 行首同时含 Tab 与空格 → 计为"Tab+Space 混合行"；
    * 文件级归类：仅有 Tab → Tab；仅有空格 → Space；两者皆有或
      存在混合行 → 混用；完全没有缩进行 → 无缩进。

示例命令：
    python -I indent-style-report.py src/
    python -I indent-style-report.py . --ext .py,.js --top 10
    python -I indent-style-report.py main.py

退出码：0 正常；2 参数或路径错误。仅依赖 Python 标准库。
"""

import argparse
import os
import re
import sys
import unicodedata
from collections import Counter

DEFAULT_EXCLUDES = {
    ".git", ".svn", ".hg", "__pycache__", "node_modules", "venv", ".venv",
    "dist", "build", ".idea", ".vscode", ".tox", ".mypy_cache",
}

DEFAULT_EXT_SPEC = (
    ".py,.pyw,.js,.mjs,.cjs,.ts,.tsx,.jsx,.java,.kt,.kts,.scala,.go,.rs,"
    ".c,.h,.cpp,.hpp,.cc,.cxx,.cs,.swift,.rb,.php,.pl,.lua,.dart,.groovy,"
    ".sh,.bash,.zsh,.ps1,.bat,.cmd,.sql,.html,.htm,.css,.scss,.less,.vue,"
    ".json,.yaml,.yml,.toml,.ini,.cfg,.conf,.xml,.md"
)

INDENT_RE = re.compile(r"^[ \t]*")


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


def _rel(path, root):
    if os.path.isdir(root):
        try:
            return os.path.relpath(path, root).replace(os.sep, "/")
        except ValueError:
            pass
    return path.replace(os.sep, "/")


def analyze_file(path):
    """统计单个文件的缩进行；二进制文件返回 None。"""
    with open(path, "rb") as f:
        head = f.read(8192)
        if b"\x00" in head:
            return None
        f.seek(0)
        text = f.read().decode("utf-8", errors="replace")
    tab = space = both = plain = blank = 0
    mixed_at = []
    for idx, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            blank += 1
            continue
        ws = INDENT_RE.match(line).group(0)
        has_t = "\t" in ws
        has_s = " " in ws
        if has_t and has_s:
            both += 1
            if len(mixed_at) < 1000:
                mixed_at.append(idx)
        elif has_t:
            tab += 1
        elif has_s:
            space += 1
        else:
            plain += 1
    return {"tab": tab, "space": space, "both": both, "plain": plain,
            "blank": blank, "mixed_at": mixed_at}


def style_of(info):
    if info["both"] or (info["tab"] and info["space"]):
        return "混用"
    if info["tab"]:
        return "Tab"
    if info["space"]:
        return "Space"
    return "无缩进"


def _pct(part, total):
    return "%.1f%%" % (100.0 * part / total) if total else "-"


def main(argv=None):
    _reconfigure_stdio()
    ap = argparse.ArgumentParser(
        prog="indent-style-report",
        description="统计目录内 Tab 与空格缩进的使用比例及混用文件清单。")
    ap.add_argument("path", help="要体检的文件或目录")
    ap.add_argument("--ext", default=DEFAULT_EXT_SPEC,
                    help="仅统计这些扩展名（逗号分隔；'*'=全部文件）")
    ap.add_argument("--top", type=int, default=20,
                    help="文件明细表最多显示 N 行（0=全部，默认 20）")
    ap.add_argument("--show", type=int, default=5,
                    help="每个混用文件最多列出多少个混合行行号（默认 5）")
    ap.add_argument("--exclude", default="", help="额外排除的目录名（逗号分隔）")
    args = ap.parse_args(argv)

    if not os.path.exists(args.path):
        print("错误：路径不存在：%s" % args.path, file=sys.stderr)
        return 2

    excludes = set(DEFAULT_EXCLUDES)
    excludes |= {x.strip() for x in args.exclude.split(",") if x.strip()}
    exts = parse_exts(args.ext)

    report = []
    n_bin = 0
    for path in iter_files(args.path, exts, excludes):
        try:
            info = analyze_file(path)
        except OSError as exc:
            print("警告：无法读取 %s：%s" % (path, exc), file=sys.stderr)
            continue
        if info is None:
            n_bin += 1
            continue
        report.append((_rel(path, args.path), info))

    tot_tab = sum(i["tab"] for _, i in report)
    tot_space = sum(i["space"] for _, i in report)
    tot_both = sum(i["both"] for _, i in report)
    tot_plain = sum(i["plain"] for _, i in report)
    tot_blank = sum(i["blank"] for _, i in report)
    n_indented = tot_tab + tot_space + tot_both

    print("== 缩进风格体检：%s ==" % args.path)
    print("扫描文件 %d 个（二进制跳过 %d 个）" % (len(report), n_bin))
    print()
    print("整体（有效缩进行 %d 行）：" % n_indented)
    print("  Tab 缩进行        %6d  %s" % (tot_tab, _pct(tot_tab, n_indented)))
    print("  空格缩进行        %6d  %s" % (tot_space, _pct(tot_space, n_indented)))
    print("  Tab+Space 混合行  %6d  %s" % (tot_both, _pct(tot_both, n_indented)))
    print("  （另有顶格行 %d 行、空白行 %d 行，不计入比例）" % (tot_plain, tot_blank))

    cats = Counter(style_of(i) for _, i in report)
    print()
    print("文件风格归类（共 %d 个）：" % len(report))
    for k in ("Tab", "Space", "混用", "无缩进"):
        if cats.get(k):
            print("  %-4s %3d 个" % (k, cats[k]))

    mixed = [(rel, i) for rel, i in report if style_of(i) == "混用"]
    if mixed:
        print()
        print("混用文件清单（%d 个）：" % len(mixed))
        for rel, i in mixed:
            extra = ""
            if i["mixed_at"]:
                extra = "；Tab+Space 行号: " + ",".join(
                    str(x) for x in i["mixed_at"][:args.show])
            print("  %s（Tab行=%d, Space行=%d, 混合行=%d%s）"
                  % (rel, i["tab"], i["space"], i["both"], extra))

    rows = [(rel, str(i["tab"]), str(i["space"]), str(i["both"]),
             str(i["plain"]), style_of(i))
            for rel, i in sorted(report,
                                 key=lambda r: -(r[1]["tab"] + r[1]["space"]
                                                 + r[1]["both"]))]
    if args.top > 0:
        rows = rows[:args.top]
    if rows:
        headers = ("文件", "Tab", "Space", "混合", "无缩进", "风格")
        widths = []
        for col, h in enumerate(headers):
            w = _dw(h)
            for r in rows:
                w = max(w, _dw(r[col]))
            widths.append(w)
        right_cols = {1, 2, 3, 4}

        def fmt(cells):
            parts = []
            for col, cell in enumerate(cells):
                gap = max(widths[col] - _dw(cell), 0)
                parts.append(" " * gap + cell if col in right_cols
                             else cell + " " * gap)
            return "  ".join(parts).rstrip()

        print()
        print("文件明细（按缩进行数降序%s）：" %
              ("，前 %d 个" % args.top if args.top and len(report) > args.top else ""))
        print(fmt(headers))
        for r in rows:
            print(fmt(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
