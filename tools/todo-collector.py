#!/usr/bin/env python3
"""TODO 收集器：扫描代码树，收集 TODO/FIXME/HACK/XXX 注释，按文件与标签分组输出清单。

用法:
    python todo-collector.py <目录> [--tags TODO,FIXME] [-e py,js] [--out FILE]

示例:
    python todo-collector.py ./src
    python todo-collector.py ./src --tags TODO,FIXME -e py,js --out todos.txt
"""
import argparse
import os
import re
import sys

DEFAULT_TAGS = ["TODO", "FIXME", "HACK", "XXX"]
SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "node_modules", ".idea", ".vscode"}


def build_pattern(tags):
    # 要求标签紧跟在注释符（# // /* -- 等）之后，行内注释也能命中，
    # 且避免把普通单词（如 "todoist"）误判为标签
    return re.compile(
        r"(?:#|//|/\*|--|;|<!--|%|')\s*\b(" + "|".join(tags) +
        r")\b[:*\s(!\[]?", re.IGNORECASE)


def iter_files(root, exts):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in sorted(filenames):
            if exts and os.path.splitext(name)[1].lstrip(".").lower() not in exts:
                continue
            yield os.path.join(dirpath, name)


def scan_file(path, pattern):
    hits = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, 1):
                stripped = line.strip()
                for m in pattern.finditer(line):
                    tag = m.group(1).upper()
                    hits.append((lineno, tag, stripped))
    except OSError as exc:
        print("warning: cannot read %s: %s" % (path, exc), file=sys.stderr)
    return hits


def main():
    ap = argparse.ArgumentParser(description="收集代码树中的 TODO/FIXME/HACK/XXX 注释")
    ap.add_argument("root", help="要扫描的目录或单个文件")
    ap.add_argument("--tags", default=",".join(DEFAULT_TAGS),
                    help="逗号分隔的标签，默认 TODO,FIXME,HACK,XXX")
    ap.add_argument("-e", "--ext", default="",
                    help="只扫描这些扩展名（逗号分隔，如 py,js）；默认全部")
    ap.add_argument("--out", help="结果写入文件（默认打印到 stdout）")
    args = ap.parse_args()

    if not os.path.exists(args.root):
        print("error: path not found: %s" % args.root, file=sys.stderr)
        return 2

    tags = [t.strip().upper() for t in args.tags.split(",") if t.strip()]
    exts = {e.strip().lower() for e in args.ext.split(",") if e.strip()}
    pattern = build_pattern(tags)

    by_file = {}    # file -> list of (lineno, tag, text)
    by_tag = {}     # tag -> list of (file, lineno, text)
    total = 0
    for path in iter_files(args.root, exts):
        for lineno, tag, text in scan_file(path, pattern):
            rel = os.path.relpath(path)
            by_file.setdefault(rel, []).append((lineno, tag, text))
            by_tag.setdefault(tag, []).append((rel, lineno, text))
            total += 1

    lines = []
    lines.append("TODO 收集结果: 共 %d 条 (标签: %s)" % (total, ", ".join(tags)))
    lines.append("=" * 60)
    lines.append("")
    lines.append("[按文件分组]")
    for f in sorted(by_file):
        lines.append("%s (%d 条)" % (f, len(by_file[f])))
        for lineno, tag, text in by_file[f]:
            lines.append("  L%-6d [%s] %s" % (lineno, tag, text))
        lines.append("")
    lines.append("[按标签分组]")
    for t in sorted(by_tag):
        lines.append("%s: %d 条" % (t, len(by_tag[t])))
        for rel, lineno, text in by_tag[t]:
            lines.append("  %s:%d  %s" % (rel, lineno, text))
        lines.append("")

    out = "\n".join(lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
        print("written %s (%d hits)" % (args.out, total))
    else:
        print(out)
    return 0 if total >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
