#!/usr/bin/env python3
"""TODO 工单提取（todo-ticket-link）——从 TODO 文本中提取工单号并生成工单关联清单。

在 TODO/FIXME/HACK 等标记行中查找工单号，支持两种常见格式：
  * JIRA 风格: ABC-456（大写字母开头的项目 key-数字，整词匹配）
  * 短井号风格: #123
按工单号分组输出关联的 文件:行号 与原文片段，便于反查"某个工单还有哪些待办"。
默认只扫描含标记关键字的行（--all 可扫描所有行）。仅依赖 Python 标准库。

用法:
    python todo-ticket-link.py [路径...] [--markers TODO,FIXME] [--all] [--ignore-case]

示例:
    python todo-ticket-link.py src/ --markers TODO,FIXME

自测（构造临时示例文件）:
    python -I todo-ticket-link.py --self-test
"""

from __future__ import annotations

import argparse
import os
import re
import sys

DEFAULT_MARKERS = ["TODO", "FIXME", "HACK", "XXX", "BUG", "NOTE",
                   "OPTIMIZE", "WORKAROUND", "REVIEW"]

JIRA_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d{1,6})\b")
HASH_RE = re.compile(r"(?<![\w#&])#(\d{1,6})\b")

SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__",
             ".venv", "venv", ".tox", "dist", "build", ".idea", ".vscode"}
MAX_FILE_SIZE = 2 * 1024 * 1024


def read_lines(path):
    """把文件读成文本行；二进制（含 NUL）或超过大小上限时返回 None。"""
    try:
        with open(path, "rb") as f:
            data = f.read(MAX_FILE_SIZE + 1)
    except OSError:
        return None
    if b"\x00" in data or len(data) > MAX_FILE_SIZE:
        return None
    return data.decode("utf-8", errors="replace").splitlines()


def iter_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for name in sorted(files):
                    yield os.path.join(root, name)


def extract_tickets(text):
    """返回一行文本中的工单号列表，如 ["PROJ-42", "#123"]。"""
    tickets = [m.group(1) for m in JIRA_RE.finditer(text)]
    tickets += ["#" + m.group(1) for m in HASH_RE.finditer(text)]
    return tickets


def collect_links(paths, markers, ignore_case=False, all_lines=False):
    """返回 (工单 -> [(文件, 行号, 片段)], 统计信息)。"""
    flags = re.IGNORECASE if ignore_case else 0
    marker_rx = None
    if markers:
        marker_rx = re.compile(r"\b(?:%s)\b" % "|".join(re.escape(m) for m in markers),
                               flags)
    links = {}
    marker_lines = 0
    ticket_lines = 0
    nfiles = 0
    for path in iter_files(paths):
        lines = read_lines(path)
        if lines is None:
            continue
        nfiles += 1
        for i, text in enumerate(lines, 1):
            if not all_lines and not (marker_rx and marker_rx.search(text)):
                continue
            marker_lines += 1
            tickets = extract_tickets(text)
            if not tickets:
                continue
            ticket_lines += 1
            snippet = text.strip()
            for t in tickets:
                links.setdefault(t, []).append((path, i, snippet))
    return links, {"marker_lines": marker_lines, "ticket_lines": ticket_lines,
                   "files": nfiles}


def render(links, stats):
    ordered = sorted(links.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    for ticket, refs in ordered:
        print("%s  (%d 处)" % (ticket, len(refs)))
        for path, line, snippet in refs:
            print("    %s:%d  %s" % (path, line, snippet[:100]))
    if not ordered:
        print("未发现工单号")
    print("---")
    print("扫描 %d 个文件, 标记行 %d 行, 其中 %d 行含工单号, 共 %d 个工单"
          % (stats["files"], stats["marker_lines"], stats["ticket_lines"], len(links)))


def self_test():
    """构造临时示例文件，断言 JIRA/井号工单都能提取、无标记的行不被误扫。"""
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="todo-ticket-")
    try:
        with open(os.path.join(tmp, "a.py"), "w", encoding="utf-8") as f:
            f.write("# TODO: fix crash on empty input, ticket PROJ-42\n"
                    "# FIXME: wrong rounding (#123)\n"
                    "# NOTE: no ticket on this line\n")
        with open(os.path.join(tmp, "b.js"), "w", encoding="utf-8") as f:
            f.write("// TODO PROJ-42 again and also #123\n"
                    "// plain comment mentions PROJ-99 but no marker keyword\n")
        links, stats = collect_links([tmp], DEFAULT_MARKERS)
        counts = {t: len(refs) for t, refs in links.items()}
        assert counts == {"PROJ-42": 2, "#123": 2}, \
            "工单应恰为 PROJ-42 x2 / #123 x2, 实际 %s" % counts
        assert "PROJ-99" not in links, "无标记关键字的行不应被扫描"
        assert stats["marker_lines"] == 4, "标记行应 4 行, 实际 %d" % stats["marker_lines"]
        assert stats["ticket_lines"] == 3, "含工单号的标记行应 3 行, 实际 %d" % stats["ticket_lines"]
        render(links, stats)
        print("工单提取断言全部通过（PROJ-42/#123 各 2 处，未标记行未误扫）")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if "--self-test" in argv:
        argv = [a for a in argv if a != "--self-test"]
        try:
            rc = self_test()
        except AssertionError as exc:
            print("SELF-TEST FAIL: %s" % exc)
            return 1
        except Exception as exc:
            print("SELF-TEST FAIL: %s: %s" % (type(exc).__name__, exc))
            return 1
        print("SELF-TEST PASS")
        return rc
    parser = argparse.ArgumentParser(
        description="TODO 工单提取：从 TODO 标记行提取工单号（ABC-456 / #123）并生成关联清单")
    parser.add_argument("paths", nargs="*", default=["."],
                        help="要扫描的文件或目录（默认当前目录）")
    parser.add_argument("--markers", default=",".join(DEFAULT_MARKERS),
                        help="逗号分隔的标记关键字（默认 TODO,FIXME,HACK,XXX,BUG,NOTE,OPTIMIZE,WORKAROUND,REVIEW）")
    parser.add_argument("--all", action="store_true",
                        help="扫描所有行而不只是含标记关键字的行")
    parser.add_argument("--ignore-case", action="store_true",
                        help="标记关键字不区分大小写")
    args = parser.parse_args(argv)
    markers = [m for m in re.split(r"[\s,]+", args.markers.strip()) if m]
    links, stats = collect_links(args.paths, markers,
                                 ignore_case=args.ignore_case, all_lines=args.all)
    render(links, stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
