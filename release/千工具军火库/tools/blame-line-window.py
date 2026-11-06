#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""blame-line-window.py — 行级 blame 查看

用途:
    解析 git blame 输出(支持 --porcelain 与默认人读两种格式),
    只显示指定行区间内各行的最后修改者、提交与内容, 并按作者/提交数汇总。
    行号按 blame 目标文件的最终行号计(1 起, 闭区间)。

示例命令:
    git blame foo.py | python blame-line-window.py --start 10 --end 30
    git blame --porcelain foo.py | python blame-line-window.py --start 10 --end 30
    python blame-line-window.py --file blame.txt --start 1 --end 20 --json
    git blame foo.py | python blame-line-window.py      # 不给区间 = 整个文件
    python blame-line-window.py --selftest

说明:
    porcelain 格式(porcelain/line-porcelain)自动识别且信息最全(含 summary);
    人读格式通过 "sha (作者 日期 行号) 内容" 的正则解析, 根提交(boundary)
    行的 "^sha" 前缀同样可解析, 不会因此把整段输入误判为不可解析。
    未提交的行(Not Committed Yet, 全 0 sha)同样正常显示。

退出码:
    0 = 正常(未解析出记录时给出提示, 也算正常)
    2 = 用法或 IO 错误
"""

import argparse
import json
import re
import sys
from datetime import datetime

PORC_HEAD_RE = re.compile(r"^([0-9a-f]{40}) (\d+) (\d+)(?: (\d+))?$")
HUMAN_RE = re.compile(
    r"^(?P<boundary>\^)?(?P<sha>[0-9a-f]{7,40})\s+\((?P<author>.+?)\s+"
    r"(?P<date>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?(?:\s+[+-]\d{4})?)\s+"
    r"(?P<line>\d+)\)(?P<rest>.*)$")


def _fmt_time(ts):
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
    except (ValueError, OverflowError, OSError):
        return ""


def _parse_porcelain(lines):
    """解析 git blame --porcelain / --line-porcelain 输出。

    提交元数据(author/summary 等)只在每个 commit 首次出现的 hunk 给出,
    后续 hunk 只有头行和内容; 按 sha 缓存补全, 避免同提交后续行丢失作者。
    """
    recs = {}
    details = {}
    i, n = 0, len(lines)
    while i < n:
        m = PORC_HEAD_RE.match(lines[i])
        if not m:
            i += 1
            continue
        sha = m.group(1)
        orig = int(m.group(2))
        final = int(m.group(3))
        size = int(m.group(4) or 1)
        i += 1
        meta = {}
        while i < n and not lines[i].startswith("\t"):
            key, _, val = lines[i].partition(" ")
            if key not in meta:
                meta[key] = val
            i += 1
        if "author" in meta:
            details[sha] = meta
        meta = details.get(sha, meta)
        contents = []
        while i < n and lines[i].startswith("\t"):
            contents.append(lines[i][1:])
            i += 1
        for k in range(size):
            recs[final + k] = {
                "sha": sha,
                "author": meta.get("author") or "?",
                "date": _fmt_time(meta.get("author-time", "")),
                "summary": meta.get("summary") or "",
                "orig_line": orig + k,
                "content": contents[k] if k < len(contents) else "",
            }
    return recs


def _parse_human(lines):
    """解析默认人读格式: <sha> (<author> <date> <lineno>) <content>。"""
    recs = {}
    for line in lines:
        m = HUMAN_RE.match(line)
        if not m:
            continue
        rest = m.group("rest")
        if rest.startswith(" "):
            rest = rest[1:]
        recs[int(m.group("line"))] = {
            "sha": m.group("sha"),
            "author": m.group("author"),
            "date": m.group("date"),
            "summary": "",
            "orig_line": 0,
            "content": rest,
        }
    return recs


def parse_blame(text):
    """自动识别 porcelain / 人读格式, 返回 {最终行号: record}。

    格式判定取"首个能匹配任一格式的非空行", 而非仅看第一个非空行:
    根提交(boundary)的人读行带 ^ 前缀, 首行可能不匹配但后续行匹配。
    """
    lines = text.splitlines()
    for line in lines:
        if not line.strip():
            continue
        if PORC_HEAD_RE.match(line):
            return _parse_porcelain(lines)
        if HUMAN_RE.match(line):
            return _parse_human(lines)
    return {}


def window(recs, start=None, end=None):
    """取 [start, end] 行区间(缺省全文件), 返回 (按行号排序的记录列表, (lo, hi))。"""
    lo = start if start is not None else 1
    hi = end if end is not None else (max(recs) if recs else 0)
    rows = []
    for ln in sorted(recs):
        if lo <= ln <= hi:
            r = dict(recs[ln])
            r["line"] = ln
            rows.append(r)
    return rows, (lo, hi)


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def run_selftest():
    failures = []

    def check(name, cond, extra=""):
        print(("PASS " if cond else "FAIL ") + name + ((" -- " + extra) if extra else ""))
        if not cond:
            failures.append(name)

    sha1 = "a" * 40
    sha2 = "b" * 40
    porc = (
        "%s 1 1 2\n" % sha1
        + "author Alice\n"
        + "author-mail <a@x>\n"
        + "author-time 1714500000\n"
        + "author-tz +0800\n"
        + "committer Bob\n"
        + "committer-mail <b@x>\n"
        + "committer-time 1714500001\n"
        + "committer-tz +0800\n"
        + "summary first commit\n"
        + "filename foo.py\n"
        + "\timport os\n"
        + "\timport sys\n"
        + "%s 3 3 1\n" % sha2
        + "author Carol\n"
        + "author-time 1714600000\n"
        + "author-tz +0800\n"
        + "committer Carol\n"
        + "committer-time 1714600000\n"
        + "committer-tz +0800\n"
        + "summary add main\n"
        + "filename foo.py\n"
        + "\tdef main():\n"
    )
    recs = parse_blame(porc)
    check("porcelain: 3 lines", sorted(recs) == [1, 2, 3], repr(sorted(recs)))
    check("porcelain: line1 author Alice", recs.get(1, {}).get("author") == "Alice")
    check("porcelain: line3 author Carol", recs.get(3, {}).get("author") == "Carol")
    check("porcelain: line2 content", recs.get(2, {}).get("content") == "import sys")
    check("porcelain: summary kept", recs.get(3, {}).get("summary") == "add main")
    rows, lohi = window(recs, 2, 3)
    check("window 2-3", [r["line"] for r in rows] == [2, 3] and lohi == (2, 3))

    # porcelain 元数据只在 commit 首个 hunk 出现, 后续 hunk 应按 sha 缓存补全
    porc2 = (
        "%s 1 1 2\n" % sha1
        + "author Alice\n"
        + "author-time 1714500000\n"
        + "author-tz +0800\n"
        + "summary first commit\n"
        + "boundary\n"
        + "filename foo.py\n"
        + "\timport os\n"
        + "\timport sys\n"
        + "%s 3 3\n" % sha2
        + "author Bob\n"
        + "author-time 1714600000\n"
        + "author-tz +0800\n"
        + "summary add main\n"
        + "filename foo.py\n"
        + "\tdef main():\n"
        + "%s 4 4\n" % sha2
        + "\tdef run():\n"
    )
    recs4 = parse_blame(porc2)
    check("porcelain-repeat: 4 lines", sorted(recs4) == [1, 2, 3, 4],
          repr(sorted(recs4)))
    check("porcelain-repeat: boundary block ok", recs4.get(1, {}).get("author") == "Alice")
    check("porcelain-repeat: cached author", recs4.get(4, {}).get("author") == "Bob")
    check("porcelain-repeat: cached summary", recs4.get(4, {}).get("summary") == "add main")
    check("porcelain-repeat: content", recs4.get(4, {}).get("content") == "def run():")

    human = (
        "aaaaaaaa1234567890aaaaaaaa1234567890aaaa (Alice 2024-05-01 10:20:30 +0800 1) import os\n"
        "bbbbbbbb1234567890bbbbbbbb1234567890bbbb (Not Committed Yet 2024-05-02 11:00:00 +0800 2) import sys\n"
    )
    recs2 = parse_blame(human)
    check("human: 2 lines", sorted(recs2) == [1, 2], repr(sorted(recs2)))
    check("human: author", recs2.get(1, {}).get("author") == "Alice")
    check("human: uncommitted author", recs2.get(2, {}).get("author") == "Not Committed Yet")
    check("human: content", recs2.get(2, {}).get("content") == "import sys")
    # 根提交(boundary)行带 ^ 前缀, 且可能恰好出现在首行: 不应导致整段返回 {}
    human_b = (
        "^45bcf81 (Alice 2024-05-01 10:20:30 +0800 1) import os\n"
        "bbbbbbbb1234567890bbbbbbbb1234567890bbbb (Bob 2024-05-02 11:00:00 +0800 12) import sys\n"
        "^45bcf81 (Alice 2024-05-01 10:20:30 +0800 25) def main():\n"
    )
    recs3 = parse_blame(human_b)
    check("human-boundary: ^ lines parsed", sorted(recs3) == [1, 12, 25],
          repr(sorted(recs3)))
    check("human-boundary: sha w/o caret", recs3.get(1, {}).get("sha") == "45bcf81")
    check("human-boundary: author", recs3.get(1, {}).get("author") == "Alice")
    check("human-boundary: normal line kept", recs3.get(12, {}).get("author") == "Bob")
    check("human-boundary: content", recs3.get(25, {}).get("content") == "def main():")
    check("unparseable -> empty", parse_blame("hello world\n") == {})

    print("selftest %s" % ("OK" if not failures else "FAILED: %s" % ", ".join(failures)))
    return 0 if not failures else 1


def main(argv=None):
    _utf8_stdio()
    ap = argparse.ArgumentParser(
        prog="blame-line-window.py",
        description="解析 git blame 输出, 查看指定行区间各自的最后修改者与提交")
    ap.add_argument("input", nargs="?", help="blame 输出文件(缺省读 stdin)")
    ap.add_argument("--file", dest="file", help="同 positional, 二选一")
    ap.add_argument("--start", type=int, help="起始行(1 起, 闭区间, 含)")
    ap.add_argument("--end", type=int, help="结束行(含)")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--no-summary", action="store_true", help="不输出作者/提交汇总")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = ap.parse_args(argv)

    if args.selftest:
        return run_selftest()

    path = args.file or args.input
    try:
        text = sys.stdin.read() if path is None else read_text(path)
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    start, end = args.start, args.end
    if start is not None and end is not None and start > end:
        start, end = end, start
    recs = parse_blame(text)
    rows, (lo, hi) = window(recs, start, end)

    if args.json:
        authors = {}
        for r in rows:
            authors[r["author"]] = authors.get(r["author"], 0) + 1
        print(json.dumps({"window": [lo, hi], "lines": rows,
                          "commits": len({r["sha"] for r in rows}),
                          "authors": authors}, ensure_ascii=False, indent=2))
        return 0

    if not rows:
        print("(no blame records in window %d-%d; "
              "期望输入: git blame 或 git blame --porcelain 的输出)" % (lo, hi))
        return 0
    for r in rows:
        print("%4d  %-8s  %-16s  %-10s  %s"
              % (r["line"], r["sha"][:8], r["author"][:16], r["date"][:10], r["content"]))
    if not args.no_summary:
        authors = {}
        for r in rows:
            authors[r["author"]] = authors.get(r["author"], 0) + 1
        print("-- window %d-%d: %d line(s), %d commit(s)"
              % (lo, hi, len(rows), len({r["sha"] for r in rows})))
        for name, cnt in sorted(authors.items(), key=lambda kv: (-kv[1], kv[0])):
            print("   %-16s %3d line(s)" % (name[:16], cnt))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
