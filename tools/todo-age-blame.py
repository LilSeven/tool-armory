#!/usr/bin/env python3
"""TODO 存在时长（todo-age-blame）——结合 git blame 计算每个 TODO 标记已存在多少天。

扫描指定路径下的文本文件，找出 TODO/FIXME 标记所在行，再用
`git blame --porcelain` 查出该行最后一次被提交的时间，算出标记的"账龄"（天），
按账龄从旧到新排列，帮助找出陈年旧账。仅依赖 Python 标准库（git 命令需在
PATH 中）；非 git 管理的文件账龄显示为 [-----]。

用法:
    python todo-age-blame.py [路径...] [--since N] [--top N]

示例:
    python todo-age-blame.py src/ --since 90 --top 20

自测（构造临时 git 仓库作为安全示例输入）:
    python -I todo-age-blame.py --self-test
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

MARKER_RE = re.compile(r"\b(TODO|FIXME)\b")

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


def collect_markers(path):
    """返回文件中的标记 [(行号, 标记词, 行文本), ...]。"""
    lines = read_lines(path)
    if lines is None:
        return []
    found = []
    for i, text in enumerate(lines, 1):
        m = MARKER_RE.search(text)
        if m:
            found.append((i, m.group(1), text))
    return found


def git_blame(path):
    """对单个文件执行 git blame --porcelain。

    返回 {行号: {"time": 秒级时间戳或 None, "author": str, "sha": str}}；
    文件不在 git 仓库中或命令失败时返回 None。
    """
    workdir = os.path.dirname(os.path.abspath(path)) or "."
    try:
        proc = subprocess.run(
            ["git", "blame", "--porcelain", "--", os.path.basename(path)],
            cwd=workdir, capture_output=True, text=True, errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    commits = {}   # sha -> 信息
    line_map = {}  # 当前行号 -> sha
    cur_sha = None
    for raw in proc.stdout.splitlines():
        if raw.startswith("\t"):
            continue  # 行内容
        parts = raw.split()
        if (len(parts) >= 3 and re.fullmatch(r"[0-9a-f]{40}", parts[0])
                and parts[1].isdigit() and parts[2].isdigit()):
            cur_sha = parts[0]
            info = commits.setdefault(cur_sha, {"time": None, "author": "?"})
            info["sha"] = cur_sha
            final = int(parts[2])
            count = int(parts[3]) if len(parts) >= 4 and parts[3].isdigit() else 1
            for ln in range(final, final + count):
                line_map[ln] = cur_sha
        elif cur_sha and len(parts) >= 2:
            if parts[0] == "author-time":
                try:
                    commits[cur_sha]["time"] = int(parts[1])
                except ValueError:
                    pass
            elif parts[0] == "author":
                commits[cur_sha]["author"] = " ".join(parts[1:]) or "?"
    return {ln: commits[sha] for ln, sha in line_map.items()}


def collect_entries(paths, since=None):
    """汇总所有标记及其账龄；since 不为 None 时只保留账龄 >= since 的条目。"""
    entries = []
    for path in iter_files(paths):
        marks = collect_markers(path)
        if not marks:
            continue
        blame = git_blame(path)
        now = time.time()
        for lineno, tag, text in marks:
            info = blame.get(lineno) if blame else None
            age = None
            if info and info.get("time"):
                age = int((now - info["time"]) // 86400)
            if since is not None and (age is None or age < since):
                continue
            entries.append({"path": path, "line": lineno, "tag": tag,
                            "text": text.strip(), "age": age, "info": info or {}})
    return entries


def fmt_age(days):
    return "[%4dd]" % days if days is not None else "[-----]"


def render(entries, top=None):
    entries = sorted(entries, key=lambda e: (e["age"] is None, -(e["age"] or 0),
                                             e["path"], e["line"]))
    for e in (entries if top is None else entries[:top]):
        info = e["info"]
        if e["age"] is None:
            origin = "未提交/非git"
        else:
            when = datetime.fromtimestamp(info["time"], tz=timezone.utc).strftime("%Y-%m-%d")
            origin = "%s %s %s" % (when, info.get("author", "?"), info.get("sha", "")[:7])
        print("%s %s:%d  %s  (%s)" % (fmt_age(e["age"]), e["path"], e["line"],
                                      e["text"][:100], origin))
    print("---")
    print("共 %d 个 TODO/FIXME 标记" % len(entries))
    ages = [e["age"] for e in entries if e["age"] is not None]
    if ages:
        print("账龄: 最老 %d 天, 平均 %d 天" % (max(ages), sum(ages) // len(ages)))
    unknown = sum(1 for e in entries if e["age"] is None)
    if unknown:
        print("其中 %d 个无法确定时间（未提交或非 git 文件）" % unknown)


def self_test():
    """构造临时 git 仓库（一条 400 天前的老 TODO + 一条刚提交的 TODO + 一个非 git 文件）并断言账龄。"""
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="todo-age-blame-")
    try:
        repo = os.path.join(tmp, "repo")
        os.makedirs(repo)

        def git(*args, env_date=None):
            env = dict(os.environ)
            if env_date:
                env["GIT_AUTHOR_DATE"] = env_date
                env["GIT_COMMITTER_DATE"] = env_date
            proc = subprocess.run(["git", "-C", repo] + list(args), capture_output=True,
                                  text=True, errors="replace", env=env, timeout=60)
            assert proc.returncode == 0, "git %s 失败: %s" % (args[0], proc.stderr.strip())
            return proc

        git("init", "-q")
        git("config", "user.email", "test@example.com")
        git("config", "user.name", "Tester")
        old_date = (datetime.now(timezone.utc) - timedelta(days=400)).strftime(
            "%Y-%m-%dT%H:%M:%S+0000")
        code = os.path.join(repo, "code.py")
        with open(code, "w", encoding="utf-8") as f:
            f.write("# TODO old-debt: rewrite the parser\n\ndef add(a, b):\n    return a + b\n")
        git("add", ".")
        git("commit", "-q", "-m", "initial", env_date=old_date)
        with open(code, "a", encoding="utf-8") as f:
            f.write("\n# TODO fresh: check edge cases\n")
        git("commit", "-q", "-am", "add fresh todo")
        plain = os.path.join(tmp, "plain.txt")
        with open(plain, "w", encoding="utf-8") as f:
            f.write("# TODO outside-repo\n")

        entries = collect_entries([tmp])
        assert len(entries) == 3, "应找到 3 个标记, 实际 %d" % len(entries)

        def find(key):
            for e in entries:
                if key in e["text"]:
                    return e
            raise AssertionError("未找到包含 %r 的标记" % key)

        old = find("old-debt")
        fresh = find("fresh")
        outside = find("outside-repo")
        assert 395 <= old["age"] <= 400, "老 TODO 账龄应约 400 天, 实际 %s" % old["age"]
        assert 0 <= fresh["age"] <= 1, "新 TODO 账龄应约 0 天, 实际 %s" % fresh["age"]
        assert outside["age"] is None, "非 git 文件账龄应为 None"
        render(entries)
        print("账龄断言全部通过（老=%.0f 天量级, 新=%d 天, 非 git 文件为空）"
              % (old["age"], fresh["age"]))
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
        description="TODO 存在时长：结合 git blame 计算每个 TODO/FIXME 标记已存在多少天")
    parser.add_argument("paths", nargs="*", default=["."],
                        help="要扫描的文件或目录（默认当前目录）")
    parser.add_argument("--since", type=int, default=None, metavar="N",
                        help="只显示账龄 >= N 天的标记")
    parser.add_argument("--top", type=int, default=None, metavar="N",
                        help="只显示最老的 N 条")
    args = parser.parse_args(argv)
    entries = collect_entries(args.paths, since=args.since)
    render(entries, top=args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
