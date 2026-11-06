#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""git log 转 JSON (gitlog2json)。

用途:
    把 git log 的文本输出解析为结构化 JSON（哈希/作者/日期/主题）。
    支持两种输入：
      1) 默认 git log 输出（commit <hash> / Author: / Date: / 缩进主题）；
      2) 竖线分隔格式，如 `git log --pretty=format:'%H|%an|%ad|%s' --date=iso`，
         每行一条记录（可用 --sep 换分隔符）。分隔格式自动识别，也可 --force-pipe。

示例命令:
    git log --pretty=format:'%H|%an|%ad|%s' --date=iso | python -I gitlog2json.py -o commits.json
    python -I gitlog2json.py gitlog.txt --format pipe
    git log --date=iso > log.txt && python -I gitlog2json.py log.txt
    python -I gitlog2json.py --self-test
"""
import argparse
import json
import re
import sys

PIPE_RE = re.compile(r"^(?P<hash>[0-9a-fA-F]{7,40})\|(?P<author>[^|]*)\|(?P<date>[^|]*)\|(?P<subject>.*)$")
COMMIT_RE = re.compile(r"^commit\s+(?P<merge>merged)?\s*(?P<hash>[0-9a-fA-F]{7,40})")
AUTHOR_RE = re.compile(r"^Author:\s*(?P<author>.+?)\s*<[^>]*>\s*$")
DATE_RE = re.compile(r"^Date:\s*(?P<date>.+)$")


def parse_pipe(lines, sep="|"):
    commits = []
    for line in lines:
        line = line.rstrip("\r\n")
        if not line.strip():
            continue
        parts = line.split(sep, 3)
        if len(parts) != 4 or not re.fullmatch(r"[0-9a-fA-F]{7,40}", parts[0]):
            continue
        commits.append({"hash": parts[0], "author": parts[1],
                        "date": parts[2], "subject": parts[3]})
    return commits


def parse_default(lines):
    commits = []
    cur = None
    stage = None  # None / 'author' / 'date' / 'subject'
    for raw in lines:
        line = raw.rstrip("\r\n")
        m = COMMIT_RE.match(line)
        if m and not m.group("merge"):
            if cur and cur.get("hash"):
                commits.append(cur)
            cur = {"hash": m.group("hash"), "author": "", "date": "", "subject": ""}
            stage = None
            continue
        if cur is None:
            continue
        ma = AUTHOR_RE.match(line)
        if ma:
            cur["author"] = ma.group("author")
            stage = "author"
            continue
        md = DATE_RE.match(line)
        if md:
            cur["date"] = md.group("date").strip()
            stage = "date"
            continue
        if stage == "date" and line.startswith("    ") and not cur["subject"]:
            cur["subject"] = line.strip()
            stage = "subject"
        elif stage == "subject" and line.strip():
            cur["subject"] += " " + line.strip()
        elif not line.strip() and stage == "subject":
            stage = None
    if cur and cur.get("hash"):
        commits.append(cur)
    return commits


def looks_pipe(lines, sep="|"):
    hits = sum(1 for l in lines[:50] if PIPE_RE.match(l.rstrip("\r\n")))
    return hits >= 1 and hits * 2 >= sum(1 for l in lines[:50] if l.strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description="git log 输出转结构化 JSON")
    ap.add_argument("input", nargs="?", help="git log 输出文本文件；为 - 时读 stdin")
    ap.add_argument("-o", "--output", help="输出 JSON 文件（缺省 stdout）")
    ap.add_argument("--format", choices=["auto", "default", "pipe"], default="auto")
    ap.add_argument("--sep", default="|", help="pipe 格式分隔符（默认 |）")
    ap.add_argument("--self-test", action="store_true", help="运行内置自测")
    args = ap.parse_args(argv)

    if args.self_test:
        pipe_sample = [
            "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0|Alice|2026-01-02 03:04:05 +0800|fix: 修复登录",
            "0f1e2d3c4b5a69788796a5b4c3d2e1f00918273f|Bob <b@x.com>|2026-01-01 00:00:00 +0000|init",
        ]
        commits = parse_pipe(pipe_sample)
        assert len(commits) == 2
        assert commits[0]["hash"] == "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
        assert commits[0]["author"] == "Alice"
        assert commits[0]["subject"] == "fix: 修复登录"
        default_sample = [
            "commit a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            "Author: Alice <alice@example.com>",
            "Date:   Fri Jan 2 03:04:05 2026 +0800",
            "",
            "    add feature X",
            "",
            "commit 0f1e2d3c4b5a69788796a5b4c3d2e1f00918273f",
            "Merge: 1111111 2222222",
            "Author: Bob <bob@example.com>",
            "Date:   Thu Jan 1 00:00:00 2026 +0000",
            "",
            "    initial commit",
        ]
        commits2 = parse_default(default_sample)
        assert len(commits2) == 2, commits2
        assert commits2[0]["author"] == "Alice"
        assert commits2[0]["subject"] == "add feature X"
        assert commits2[1]["subject"] == "initial commit"
        assert looks_pipe(pipe_sample) and not looks_pipe(default_sample)
        print("self-test OK")
        return 0

    if not args.input or args.input == "-":
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        lines = sys.stdin.read().splitlines()
    else:
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()

    fmt = args.format
    if fmt == "auto":
        fmt = "pipe" if looks_pipe(lines, args.sep) else "default"
    commits = parse_pipe(lines, args.sep) if fmt == "pipe" else parse_default(lines)

    out_text = json.dumps(commits, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out_text + "\n")
        print(f"[gitlog2json] 解析 {len(commits)} 条提交 -> {args.output}", file=sys.stderr)
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
