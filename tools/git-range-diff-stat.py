#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""git-range-diff-stat.py — 提交区间统计

用途:
    解析 git diff / git log -p 输出的统一 diff, 或 git diff --numstat 输出,
    汇总两个提交(或任意区间)之间改动的文件与新增/删除行数, 并给出合计。
    适合提交前快速回答"这次改动动了哪些文件、各改了多少行"。

示例命令:
    git diff HEAD~3..HEAD | python git-range-diff-stat.py
    git log -p v1.0..v1.1        | python git-range-diff-stat.py
    git diff --numstat main..feature | python git-range-diff-stat.py
    python git-range-diff-stat.py --file my.diff --sort total
    python git-range-diff-stat.py --json --file my.diff
    python git-range-diff-stat.py --selftest

支持格式:
    1) 统一 diff(git diff / git log -p / git diff -M, 含 rename/binary)
    2) numstat(每行: <adds>\\t<dels>\\t<path>, '-' 表示二进制)
    输入含多行 "数字\\t数字\\t路径" 时自动按 numstat 解析,
    也可用 --numstat / --unified 强制指定。

退出码:
    0 = 正常(空输入也算正常, 输出 no changes)
    2 = 用法或 IO 错误
"""

import argparse
import json
import re
import sys

NUMSTAT_RE = re.compile(r"^(\d+|-)\t(\d+|-)\t(.*)$")


def _header_path(s):
    """解析 ---/+++ 头里的路径: 去引号、去 a// b/ 前缀、去 tab 后的时间戳。"""
    s = s.strip()
    if len(s) >= 2 and s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    s = s.split("\t")[0].strip()
    if s == "/dev/null":
        return s
    if re.match(r"^[ab]/", s):
        s = s[2:]
    return s


def _strip_ab(p):
    if p and p != "/dev/null" and re.match(r"^[ab]/", p):
        return p[2:]
    return p


def _diff_git_paths(line):
    """从 'diff --git a/x b/y' 提取两个路径(支持带引号)。"""
    rest = line[len("diff --git "):].strip()
    m = re.match(r'^"(.*)" "(.*)"$', rest)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"^(\S+) (\S+)$", rest)
    if m:
        return m.group(1), m.group(2)
    return None, None


def parse_unified_diff(text):
    """解析统一 diff, 返回 [(file, {"adds","dels","binary"}), ...]。

    hunk 体内的 '--- xxx' 是被删除的内容行而非文件头:
    只有在 hunk 之外遇到的 --- / +++ 才当作头部处理。
    """
    files = {}
    order = []

    def get(name):
        name = _strip_ab(name)
        if name not in files:
            files[name] = {"adds": 0, "dels": 0, "binary": False}
            order.append(name)
        return files[name]

    cur = None
    old_path = None
    in_hunk = False
    for line in text.splitlines():
        if in_hunk:
            c = line[:1]
            if c in ("+", "-"):
                if cur is not None:
                    if c == "+":
                        cur["adds"] += 1
                    else:
                        cur["dels"] += 1
                continue
            if c == " " or c == "\\" or line == "":
                continue                       # 上下文 / "\\ No newline" / 空行
            in_hunk = False                    # hunk 结束, 本行按头部继续处理
        if line.startswith("diff --git "):
            a, b = _diff_git_paths(line)
            name = _strip_ab(b) or _strip_ab(a)
            cur = get(name) if name else None
            old_path = None
            continue
        if line.startswith("@@ -"):
            in_hunk = True
            continue
        if line.startswith("--- "):
            old_path = _header_path(line[4:])
            continue
        if line.startswith("+++ "):
            new_path = _header_path(line[4:])
            name = new_path if new_path != "/dev/null" else old_path
            if name:
                cur = get(name)
            continue
        if line.startswith("Binary files ") or line == "GIT binary patch":
            if cur is not None:
                cur["binary"] = True
            continue
        # 其余头部行(index/mode/rename/similarity 等)忽略
    return [(name, files[name]) for name in order]


def _numstat_path(p):
    p = p.strip()
    if len(p) >= 2 and p.startswith('"') and p.endswith('"'):
        p = p[1:-1]
    p = re.sub(r"\{[^{}]* => ([^{}]*)\}", r"\1", p)   # dir/{old => new}/file
    if " => " in p:
        p = p.split(" => ")[-1]
    return p


def parse_numstat(text):
    files = {}
    order = []
    for line in text.splitlines():
        m = NUMSTAT_RE.match(line)
        if not m:
            continue
        a, d, raw = m.group(1), m.group(2), m.group(3)
        name = _numstat_path(raw)
        if name not in files:
            files[name] = {"adds": 0, "dels": 0, "binary": False}
            order.append(name)
        entry = files[name]
        if a == "-" or d == "-":
            entry["binary"] = True
        else:
            entry["adds"] += int(a)
            entry["dels"] += int(d)
    return [(name, files[name]) for name in order]


def looks_like_numstat(text):
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return False
    hits = sum(1 for l in lines if NUMSTAT_RE.match(l))
    return hits * 2 >= len(lines)


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

    unified = (
        "diff --git a/app.py b/app.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,5 +1,6 @@\n"
        " line1\n"
        "-old line\n"
        "+new line\n"
        "+added2\n"
        " line2\n"
        "+added3\n"
        " line3\n"
        "--- --weird\n"                      # hunk 体内被删除的内容行, 不算文件头
        "diff --git a/newmod.py b/newmod.py\n"
        "new file mode 100644\n"
        "index 0000000..3333333\n"
        "--- /dev/null\n"
        "+++ b/newmod.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+hello\n"
        "+world\n"
        "diff --git a/blob.bin b/blob.bin\n"
        "index 4444444..5555555 100644\n"
        "Binary files a/blob.bin and b/blob.bin differ\n"
    )
    entries = dict(parse_unified_diff(unified))
    check("app.py +3/-2", entries.get("app.py") == {"adds": 3, "dels": 2, "binary": False},
          repr(entries.get("app.py")))
    check("newmod.py +2/-0", entries.get("newmod.py") == {"adds": 2, "dels": 0, "binary": False})
    check("blob.bin binary", entries.get("blob.bin") == {"adds": 0, "dels": 0, "binary": True})
    check("3 files parsed", len(entries) == 3, repr(sorted(entries)))
    check("unified not detected as numstat", looks_like_numstat(unified) is False)

    numstat = "3\t1\tapp.py\n2\t0\tnewmod.py\n-\t-\tpics/logo.png\n"
    check("numstat detected", looks_like_numstat(numstat) is True)
    n = dict(parse_numstat(numstat))
    check("numstat app.py", n.get("app.py") == {"adds": 3, "dels": 1, "binary": False})
    check("numstat binary", n.get("pics/logo.png") == {"adds": 0, "dels": 0, "binary": True})
    check("numstat rename path",
          _numstat_path("src/{old => new}/mod.py") == "src/new/mod.py")

    print("selftest %s" % ("OK" if not failures else "FAILED: %s" % ", ".join(failures)))
    return 0 if not failures else 1


def main(argv=None):
    _utf8_stdio()
    ap = argparse.ArgumentParser(
        prog="git-range-diff-stat.py",
        description="解析 git diff/log -p/numstat 输出, 汇总改动文件与行数")
    ap.add_argument("input", nargs="?", help="输入文件(缺省读 stdin)")
    ap.add_argument("--file", dest="file", help="同 positional, 二选一")
    ap.add_argument("--numstat", action="store_true", help="强制按 numstat 解析")
    ap.add_argument("--unified", action="store_true", help="强制按统一 diff 解析")
    ap.add_argument("--sort", choices=["name", "total", "added", "deleted"], default="name",
                    help="排序方式(默认 name)")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
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

    if args.numstat or (not args.unified and looks_like_numstat(text)):
        entries = parse_numstat(text)
    else:
        entries = parse_unified_diff(text)

    rows = [{"file": name, "adds": e["adds"], "dels": e["dels"],
             "binary": e["binary"], "total": e["adds"] + e["dels"]}
            for name, e in entries]
    key = {
        "name": lambda r: r["file"],
        "total": lambda r: (-r["total"], r["file"]),
        "added": lambda r: (-r["adds"], r["file"]),
        "deleted": lambda r: (-r["dels"], r["file"]),
    }[args.sort]
    rows.sort(key=key)
    total_adds = sum(r["adds"] for r in rows)
    total_dels = sum(r["dels"] for r in rows)
    n_bin = sum(1 for r in rows if r["binary"])

    if args.json:
        print(json.dumps({"files": len(rows), "binary_files": n_bin,
                          "total_adds": total_adds, "total_dels": total_dels,
                          "rows": rows}, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("(no changes / empty input)")
        return 0
    width = min(max(len(r["file"]) for r in rows), 60)
    for r in rows:
        tag = "  [binary]" if r["binary"] else ""
        print("%-*s  +%4d  -%4d%s" % (width, r["file"][:60], r["adds"], r["dels"], tag))
    print("-" * (width + 16))
    print("%-*s  +%4d  -%4d   (%d file(s), %d binary)"
          % (width, "TOTAL", total_adds, total_dels, len(rows), n_bin))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
