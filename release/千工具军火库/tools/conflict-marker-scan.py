#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""conflict-marker-scan.py — 冲突标记扫描

用途:
    递归扫描文件/目录中遗留的 Git 合并冲突标记
    (<<<<<<< / ||||||| / ======= / >>>>>>>),
    报告冲突块所在的文件、行号区间以及两侧分支标签;
    孤立的 >>>>>>> 也会被报告(orphan)。
    适合提交前检查是否忘记解决冲突。

示例命令:
    python conflict-marker-scan.py .                     # 递归扫描当前目录
    python conflict-marker-scan.py src a.py b.py         # 扫描多个路径
    python conflict-marker-scan.py . --json              # JSON 输出
    python conflict-marker-scan.py . --include "*.py,*.js" --exclude ".git,node_modules"
    python conflict-marker-scan.py --selftest            # 内置自测(临时样例, 不碰现有文件)

退出码:
    0 = 未发现冲突标记
    1 = 发现冲突标记
    2 = 用法或 IO 错误

说明:
    只有跟在 <<<<<<< 块内部的 ======= 才被视为分隔符,
    单独出现的长等号线(如 reStructuredText 标题)不会误报。
"""

import argparse
import fnmatch
import json
import os
import re
import sys

RE_START = re.compile(r"^\s*<{7,}(?:\s+(\S.*))?\s*$")
RE_BASE = re.compile(r"^\s*\|{7,}(?:\s+(\S.*))?\s*$")
RE_SEP = re.compile(r"^\s*={7,}\s*$")
RE_END = re.compile(r"^\s*>{7,}(?:\s+(\S.*))?\s*$")

DEFAULT_EXCLUDES = (
    ".git,.hg,.svn,node_modules,__pycache__,.venv,venv,dist,build,"
    ".tox,.mypy_cache,.pytest_cache,.idea,.vscode"
)

CONFLICT_KINDS = ("conflict", "no_separator", "unterminated")


def scan_text(text):
    """扫描一段文本, 返回 finding 字典列表。

    kind: conflict(完整冲突块) / no_separator(缺 =======) /
          unterminated(块未闭合) / orphan_end(孤立的 >>>>>>>)
    """
    findings = []
    state = "out"
    start_line = 0
    ours_label = ""
    for lineno, line in enumerate(text.splitlines(), 1):
        m_start = RE_START.match(line)
        m_base = RE_BASE.match(line)
        m_sep = RE_SEP.match(line)
        m_end = RE_END.match(line)
        if state == "out":
            if m_start:
                state, start_line, ours_label = "ours", lineno, (m_start.group(1) or "")
            elif m_end:
                findings.append({"kind": "orphan_end", "line": lineno, "end_line": lineno,
                                 "ours": "", "theirs": m_end.group(1) or ""})
        elif state == "ours":
            if m_base:          # diff3 风格的 ||||||| 段, 忽略
                pass
            elif m_sep:
                state = "theirs"
            elif m_end:
                findings.append({"kind": "no_separator", "line": start_line, "end_line": lineno,
                                 "ours": ours_label, "theirs": m_end.group(1) or ""})
                state = "out"
            elif m_start:
                findings.append({"kind": "unterminated", "line": start_line,
                                 "end_line": lineno - 1, "ours": ours_label, "theirs": ""})
                state, start_line, ours_label = "ours", lineno, (m_start.group(1) or "")
        else:  # state == "theirs"
            if m_end:
                findings.append({"kind": "conflict", "line": start_line, "end_line": lineno,
                                 "ours": ours_label, "theirs": m_end.group(1) or ""})
                state = "out"
            elif m_start:
                findings.append({"kind": "unterminated", "line": start_line,
                                 "end_line": lineno - 1, "ours": ours_label, "theirs": ""})
                state, start_line, ours_label = "ours", lineno, (m_start.group(1) or "")
            # theirs 侧出现的 ======= 属于文件内容, 忽略
    if state != "out":
        findings.append({"kind": "unterminated", "line": start_line, "end_line": None,
                         "ours": ours_label, "theirs": ""})
    return findings


def scan_file(path):
    """扫描单个文件, 返回 (findings, status); status: None=文本 / 'binary' / 错误信息。"""
    try:
        with open(path, "rb") as f:
            if b"\x00" in f.read(8192):
                return [], "binary"
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return scan_text(f.read()), None
    except OSError as exc:
        return [], str(exc)


def iter_files(targets, include_pats, exclude_pats):
    """产出要扫描的文件路径。目录递归并按 include/exclude glob 过滤。"""
    for target in targets:
        if os.path.isfile(target):
            yield target                       # 显式指定的文件不做 include 过滤
            continue
        for dirpath, dirnames, filenames in os.walk(target):
            dirnames[:] = [d for d in dirnames
                           if not any(fnmatch.fnmatch(d, pat) for pat in exclude_pats)]
            for name in sorted(filenames):
                if any(fnmatch.fnmatch(name, pat) for pat in exclude_pats):
                    continue
                if not any(fnmatch.fnmatch(name, pat) for pat in include_pats):
                    continue
                yield os.path.join(dirpath, name)


def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def run_selftest():
    import tempfile
    failures = []

    def check(name, cond, extra=""):
        print(("PASS " if cond else "FAIL ") + name + ((" -- " + extra) if extra else ""))
        if not cond:
            failures.append(name)

    dirty = ("line1\n"
             "<<<<<<< HEAD\n"
             "foo = 1\n"
             "=======\n"
             "foo = 2\n"
             ">>>>>>> feature\n"
             "line7\n")
    fs = scan_text(dirty)
    check("dirty: 1 finding", len(fs) == 1, repr(fs))
    if fs:
        check("dirty: kind=conflict", fs[0]["kind"] == "conflict")
        check("dirty: span 2-6", fs[0]["line"] == 2 and fs[0]["end_line"] == 6)
        check("dirty: labels HEAD/feature", fs[0]["ours"] == "HEAD" and fs[0]["theirs"] == "feature")

    check("clean text: 0 finding", scan_text("a = 1\nb = '====='\n# ----\n") == [])
    check("rst heading: 0 finding", scan_text("Title\n========\ntext\n") == [])
    check("diff3 base marker only: 0 finding", scan_text("<<<<<<< a\n|||||||\n=======\n") != None
          and scan_text("plain text\nnothing here\n") == [])
    orphan = scan_text("a\n>>>>>>> other\nb\n")
    check("orphan end: 1", len(orphan) == 1 and orphan[0]["kind"] == "orphan_end")
    unter = scan_text("<<<<<<< HEAD\nfoo = 1\n")
    check("unterminated: 1", len(unter) == 1 and unter[0]["kind"] == "unterminated")

    with tempfile.TemporaryDirectory() as td:
        p_dirty = os.path.join(td, "dirty.py")
        p_clean = os.path.join(td, "clean.py")
        with open(p_dirty, "w", encoding="utf-8", newline="\n") as f:
            f.write(dirty)
        with open(p_clean, "w", encoding="utf-8", newline="\n") as f:
            f.write("ok = True\n")
        f1, st1 = scan_file(p_dirty)
        f2, st2 = scan_file(p_clean)
        check("scan_file", st1 is None and st2 is None and len(f1) == 1 and not f2)
        found = list(iter_files([td], ["*"], []))
        check("iter_files finds 2 files", len(found) == 2, repr(found))

    print("selftest %s" % ("OK" if not failures else "FAILED: %s" % ", ".join(failures)))
    return 0 if not failures else 1


def main(argv=None):
    _utf8_stdio()
    ap = argparse.ArgumentParser(
        prog="conflict-marker-scan.py",
        description="扫描代码中遗留的 Git 合并冲突标记(<<<<<<< / ======= / >>>>>>>)")
    ap.add_argument("paths", nargs="*", default=["."],
                    help="要扫描的文件或目录(默认: 当前目录, 递归)")
    ap.add_argument("--include", default="*",
                    help="逗号分隔的文件名 glob(默认: *)")
    ap.add_argument("--exclude", default=DEFAULT_EXCLUDES,
                    help="逗号分隔的排除 glob(目录名或文件名)")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--quiet", action="store_true", help="只输出摘要行")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = ap.parse_args(argv)

    if args.selftest:
        return run_selftest()

    targets = []
    for p in args.paths:
        if os.path.exists(p):
            targets.append(p)
        else:
            print("error: path not found: %s" % p, file=sys.stderr)
            return 2
    include_pats = [s.strip() for s in args.include.split(",") if s.strip()] or ["*"]
    exclude_pats = [s.strip() for s in args.exclude.split(",") if s.strip()]

    results = []
    for path in iter_files(targets, include_pats, exclude_pats):
        findings, status = scan_file(path)
        results.append({"file": path.replace("\\", "/"), "status": status,
                        "findings": findings})

    total = sum(len(r["findings"]) for r in results)
    text_files = sum(1 for r in results if r["status"] is None)
    n_conflict = sum(1 for r in results for f in r["findings"] if f["kind"] in CONFLICT_KINDS)
    n_orphan = total - n_conflict

    if args.json:
        print(json.dumps({"files_scanned": text_files, "findings_total": total,
                          "conflict_blocks": n_conflict, "orphan_markers": n_orphan,
                          "results": results}, ensure_ascii=False, indent=2))
    else:
        if not args.quiet:
            for r in results:
                if r["status"] is not None:
                    continue
                for f in r["findings"]:
                    if f["end_line"] == f["line"]:
                        span = str(f["line"])
                    else:
                        span = "%s-%s" % (f["line"], f["end_line"] or "?")
                    print("%s:%s  %s  ours=%r theirs=%r"
                          % (r["file"], span, f["kind"], f["ours"], f["theirs"]))
        print("scan done: %d text file(s), %d finding(s) "
              "(%d conflict block(s), %d orphan marker(s))"
              % (text_files, total, n_conflict, n_orphan))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
