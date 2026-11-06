#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diff统计汇总 (diff-stat-sum) —— 解析 git diff --stat / --numstat 输出, 汇总总增删行数与文件数。

用途:
    解析粘贴或重定向过来的 `git diff --stat` / `git diff --numstat` 文本,
    汇总文件总数、新增行数、删除行数、二进制文件数。两种格式可混合输入, 逐行自动识别。

说明:
    - numstat 格式: 每行 "新增<TAB>删除<TAB>路径", '-' 表示二进制文件; 增删行数精确。
    - stat 格式: "路径 | N +-" 其中 N 是该文件真实变更行数(增+删), 但 +/- 图形条
      可能因宽度被截断; 精确的增删拆分需输入末尾的汇总行
      (如 "3 files changed, 35 insertions(+), 12 deletions(-)")。
    - 支持 -M 重命名路径归一化(统计到新路径)与带引号的非 ASCII 路径。

示例命令:
    git diff --stat | python diff-stat-sum.py
    git diff --numstat HEAD~3 | python diff-stat-sum.py
    git diff --stat HEAD~5..HEAD > d.txt && python diff-stat-sum.py d.txt
    python diff-stat-sum.py a.numstat b.stat --json
    python diff-stat-sum.py --self-test

退出码:
    0 = 成功; 1 = 输入中没有可识别的 diff 行
"""

import argparse
import json
import re
import sys

NUMSTAT_RE = re.compile(r"^(\d+|-)\t(\d+|-)\t(.*)$")
SUMMARY_RE = re.compile(
    r"^\s*(\d+) files? changed"
    r"(?:,\s*(\d+) insertions?\(\+\))?"
    r"(?:,\s*(\d+) deletions?\(-\))?\s*$")
STATFILE_RE = re.compile(r"^(.+)\s+\|\s+(\d+)\s*([+-]*)\s*$")
BIN_STAT_RE = re.compile(r"\|\s+Bin\b")


def _force_utf8_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def unquote_git_path(p):
    """还原 git 对含特殊字符路径的 C 风格引号(如 "src/\\346\\265\\213.py")。"""
    if len(p) < 2 or p[0] != '"' or p[-1] != '"':
        return p
    body = p[1:-1]
    out = bytearray()
    i = 0
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            n = body[i + 1]
            simple = {"t": 9, "n": 10, "r": 13, '"': 34, "\\": 92}
            if n in simple:
                out.append(simple[n])
                i += 2
                continue
            if n.isdigit():
                j = i + 1
                digits = ""
                while j < len(body) and len(digits) < 3 and body[j] in "01234567":
                    digits += body[j]
                    j += 1
                if digits:
                    out.append(int(digits, 8))
                    i = j
                    continue
            out += n.encode("utf-8")
            i += 2
            continue
        out += c.encode("utf-8")
        i += 1
    return out.decode("utf-8", "replace")


def norm_rename(p):
    """把 numstat/stat 的重命名路径归一到新路径。

    "js/{old => new}/app.js" -> "js/new/app.js";  "a.py => b.py" -> "b.py"
    """
    if " => " not in p:
        return p
    if "{" in p:
        i = p.index("{")
        k = p.find(" => ", i)
        j = p.find("}", k)
        if k != -1 and j != -1:
            return p[:i] + p[k + 4:j] + p[j + 1:]
    return p.split(" => ", 1)[1]


def parse_diff_text(lines):
    """逐行解析, 返回 {'numstat': {...}, 'stat': {...}, 'ignored': n}。"""
    ns = {"files": 0, "added": 0, "deleted": 0, "binary": 0, "paths": []}
    st = {"files": 0, "changed_lines": 0, "binary": 0, "has_summary": False,
          "insertions": None, "deletions": None,
          "bar_insertions": 0, "bar_deletions": 0, "paths": []}
    ignored = 0
    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        m = SUMMARY_RE.match(line)
        if m:
            st["has_summary"] = True
            st["insertions"] = int(m.group(2)) if m.group(2) is not None else 0
            st["deletions"] = int(m.group(3)) if m.group(3) is not None else 0
            continue
        m = NUMSTAT_RE.match(line)
        if m:
            a, d = m.group(1), m.group(2)
            path = norm_rename(unquote_git_path(m.group(3)))
            ns["files"] += 1
            ns["paths"].append(path)
            if a == "-" or d == "-":
                ns["binary"] += 1
            else:
                ns["added"] += int(a)
                ns["deleted"] += int(d)
            continue
        m = STATFILE_RE.match(line)
        if m:
            st["files"] += 1
            st["changed_lines"] += int(m.group(2))
            st["bar_insertions"] += (m.group(3) or "").count("+")
            st["bar_deletions"] += (m.group(3) or "").count("-")
            st["paths"].append(m.group(1).strip())
            continue
        if BIN_STAT_RE.search(line):  # stat 输出中的 " | Bin 12 -> 34 bytes"
            st["binary"] += 1
            st["paths"].append(line.split("|")[0].strip())
            continue
        ignored += 1
    return {"numstat": ns, "stat": st, "ignored": ignored}


def render(res):
    ns, st = res["numstat"], res["stat"]
    total_files = ns["files"] + st["files"]
    total_binary = ns["binary"] + st["binary"]
    out = ["git diff 输出汇总", "-" * 64]
    if ns["files"]:
        out.append("numstat : 文件 {}  新增 +{}  删除 -{}  二进制 {}".format(
            ns["files"], ns["added"], ns["deleted"], ns["binary"]))
    if st["files"] or st["binary"]:
        if st["has_summary"]:
            detail = "精确 +{}/-{} (来自汇总行)".format(st["insertions"], st["deletions"])
        else:
            detail = "图形条估算 +{}/-{} (可能被截断)".format(
                st["bar_insertions"], st["bar_deletions"])
        out.append("stat    : 文件 {}  累计变更 {} 行  [{}]  二进制 {}".format(
            st["files"], st["changed_lines"], detail, st["binary"]))
    out.append("-" * 64)
    out.append("文件数  : {}{}".format(total_files,
                                      " (含二进制 {})".format(total_binary) if total_binary else ""))
    exact = ns["files"] > 0 or st["has_summary"]
    if exact:
        ins = ns["added"] + (st["insertions"] or 0)
        dele = ns["deleted"] + (st["deletions"] or 0)
        out.append("新增行数: +{}".format(ins))
        out.append("删除行数: -{}".format(dele))
    else:
        out.append("新增行数: ~+{} (近似: 无汇总行, 按图形条估算)".format(
            ns["added"] + st["bar_insertions"]))
        out.append("删除行数: ~-{} (近似: 无汇总行, 按图形条估算)".format(
            ns["deleted"] + st["bar_deletions"]))
    if res["ignored"]:
        out.append("(另有 {} 行无法识别, 已忽略)".format(res["ignored"]))
    return "\n".join(out)


def run(args, parser):
    if args.files:
        lines = []
        for fp in args.files:
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    lines.extend(f)
            except OSError as e:
                print("错误: 无法读取 {}: {}".format(fp, e), file=sys.stderr)
                return 1
    elif not sys.stdin.isatty():
        lines = sys.stdin.read().splitlines()
    else:
        parser.error("缺少输入: 请提供文件参数或通过 stdin 管道传入 git diff 输出")

    res = parse_diff_text(lines)
    recognized = res["numstat"]["files"] + res["stat"]["files"] + \
        res["numstat"]["binary"] + res["stat"]["binary"] + \
        (1 if res["stat"]["has_summary"] else 0)
    if recognized == 0:
        print("错误: 输入中没有可识别的 git diff --stat / --numstat 行。", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(render(res))
    return 0


def self_test():
    """用合成的 --stat / --numstat 文本验证解析与汇总。"""
    stat_sample = "\n".join([
        " src/main.py        | 12 ++++++---",
        " src/util/helper.py |  5 +-",
        " README.md          | 30 ++++++++++++++",
        " 3 files changed, 35 insertions(+), 12 deletions(-)",
    ])
    r1 = parse_diff_text(stat_sample.splitlines())
    assert r1["stat"]["files"] == 3, r1
    assert r1["stat"]["changed_lines"] == 47, r1  # 12+5+30
    assert r1["stat"]["has_summary"] and r1["stat"]["insertions"] == 35, r1
    assert r1["stat"]["deletions"] == 12, r1
    assert r1["numstat"]["files"] == 0 and r1["ignored"] == 0, r1

    numstat_sample = "\n".join([
        "3\t1\tsrc/main.py",
        "10\t0\tsrc/new.py",
        "-\t-\tassets/logo.png",
        "2\t2\tREADME.md",
    ])
    r2 = parse_diff_text(numstat_sample.splitlines())
    assert r2["numstat"]["files"] == 4 and r2["numstat"]["binary"] == 1, r2
    assert r2["numstat"]["added"] == 15 and r2["numstat"]["deleted"] == 3, r2

    # 混合输入
    r3 = parse_diff_text((stat_sample + "\n" + numstat_sample).splitlines())
    assert r3["numstat"]["files"] + r3["stat"]["files"] == 7, r3
    assert r3["numstat"]["added"] + r3["stat"]["insertions"] == 50, r3
    assert r3["numstat"]["deleted"] + r3["stat"]["deletions"] == 15, r3

    # 重命名归一化 + 带引号路径
    r4 = parse_diff_text([
        "1\t0\tjs/{old => new}/app.js",
        "4\t2\told_name.py => new_name.py",
        '1\t1\t"src/\\346\\265\\213\\350\\257\\225.py"',
    ])
    assert r4["numstat"]["files"] == 3 and r4["numstat"]["added"] == 6, r4
    assert "js/new/app.js" in r4["numstat"]["paths"], r4["numstat"]["paths"]
    assert "new_name.py" in r4["numstat"]["paths"], r4["numstat"]["paths"]
    assert "src/测试.py" in r4["numstat"]["paths"], r4["numstat"]["paths"]

    # stat 的 Bin 行 + 无汇总行时的近似提示
    r5 = parse_diff_text([" img.png | Bin 0 -> 5 bytes", " a.py | 4 ++--"])
    assert r5["stat"]["binary"] == 1 and r5["stat"]["files"] == 1, r5
    assert r5["stat"]["changed_lines"] == 4 and not r5["stat"]["has_summary"], r5

    print("[diff-stat-sum 自测] stat/numstat/混合/重命名/引号路径 断言全部通过")
    print()
    print(render(r3))
    print()
    print(render(r5))
    print("SELF-TEST OK")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="diff-stat-sum",
        description="diff统计汇总: 解析 git diff --stat / --numstat 输出, 汇总总增删行数与文件数。",
        epilog="示例: git diff --stat | python diff-stat-sum.py")
    parser.add_argument("files", nargs="*", help="diff 输出文本文件(缺省读 stdin)")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出解析结果")
    parser.add_argument("--self-test", action="store_true", help="运行内置自测")
    _force_utf8_stdout()
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    return run(args, parser)


if __name__ == "__main__":
    sys.exit(main())
