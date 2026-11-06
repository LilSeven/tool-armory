#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diff-noise-score.py — diff 噪音评分

用途:
    解析统一 diff(git diff / git log -p), 统计其中"纯空白/重排"类改动占比,
    给本次变更打一个 0-100 的噪音分。分类:
      - ws:       空白类(去掉所有空白后内容相同, 如缩进/行尾空白变化)
      - identical: 重排类(同一 hunk 内被删除又原样加回的行, 移动/换序)
      - blank:    空行增删
      - signal:   实质内容改动
    噪音分 = 100 * (ws+identical+blank) / 总变更行数, 分数越高说明实质改动越少。

示例命令:
    git diff HEAD~1 | python diff-noise-score.py
    python diff-noise-score.py --file my.diff
    git diff -w HEAD~1 | python diff-noise-score.py --json
    python diff-noise-score.py --file my.diff --fail-above 50   # 超 50 分退出码 1
    python diff-noise-score.py --selftest

退出码:
    0 = 正常(未指定 --fail-above, 或噪音分未超标)
    1 = 噪音分超过 --fail-above 阈值
    2 = 用法或 IO 错误

说明:
    这是启发式评分: 配对在 hunk 内进行(删除行 vs 新增行,
    按去掉空白后的文本用 difflib 对齐), 因此跨 hunk 的大范围搬移
    可能仍被记为 signal。
"""

import argparse
import difflib
import json
import re
import sys


def _norm(s):
    return " ".join(s.split())


def _header_path(s):
    s = s.strip()
    if len(s) >= 2 and s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    s = s.split("\t")[0].strip()
    if s == "/dev/null":
        return ""
    if re.match(r"^[ab]/", s):
        s = s[2:]
    return s


def parse_diff(text):
    """把统一 diff 拆成 [{"file", "hunks":[{"R":[删除行],"A":[新增行]}]}]。"""
    files = []
    by_name = {}
    cur = None
    in_hunk = False
    hunk = None
    for line in text.splitlines():
        if in_hunk:
            c = line[:1]
            if c == "-":
                hunk["R"].append(line[1:])
                continue
            if c == "+":
                hunk["A"].append(line[1:])
                continue
            if c == " " or c == "\\" or line == "":
                continue
            in_hunk = False                    # hunk 结束, 本行按头部继续处理
        if line.startswith("@@ -"):
            if cur is None:
                cur = {"file": "(unknown)", "hunks": []}
                by_name["(unknown)"] = cur
                files.append(cur)
            hunk = {"R": [], "A": []}
            cur["hunks"].append(hunk)
            in_hunk = True
            continue
        if line.startswith("+++ "):
            name = _header_path(line[4:]) or "(unknown)"
            cur = by_name.get(name)
            if cur is None:
                cur = {"file": name, "hunks": []}
                by_name[name] = cur
                files.append(cur)
            continue
        # diff --git / --- / index 等头部行忽略
    return files


def score_hunk(hunk):
    """给单个 hunk 评分, 返回各类行数统计与 score。"""
    R, A = hunk["R"], hunk["A"]
    ws = ident = blank = signal = 0

    def count_unmatched(lines):
        nonlocal blank, signal
        for x in lines:
            if x.strip():
                signal += 1
            else:
                blank += 1

    if R and A:
        sm = difflib.SequenceMatcher(a=[_norm(x) for x in R],
                                     b=[_norm(y) for y in A],
                                     autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for k in range(i2 - i1):
                    if R[i1 + k] == A[j1 + k]:
                        ident += 2             # 原样删除又加回: 重排/搬移
                    else:
                        ws += 2                # 仅空白不同: 空白类
                continue
            count_unmatched(R[i1:i2])
            count_unmatched(A[j1:j2])
    else:
        count_unmatched(R)
        count_unmatched(A)

    total = len(R) + len(A)
    noise = ws + ident + blank
    return {"changed": total, "noise": noise, "ws": ws, "identical": ident,
            "blank": blank, "signal": signal,
            "score": round(100.0 * noise / total, 1) if total else 0.0}


def verdict(score):
    if score < 10:
        return "low-noise"
    if score < 35:
        return "medium-noise"
    return "high-noise"


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

    mixed = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1,5 +1,6 @@\n"
        " import os\n"
        "-value = compute(x)\n"
        "+value = compute(x)   # recompute\n"
        "+\n"                                  # 新增空行 -> blank
        "-    if ready:\n"
        "-        run(x)\n"
        "+\tif ready:\n"                       # 缩进空格->tab -> ws
        "+\t\trun(x)\n"                        # 缩进变化 -> ws
        " print(done)\n"
    )
    files = parse_diff(mixed)
    check("mixed: 1 file 1 hunk",
          len(files) == 1 and len(files[0]["hunks"]) == 1,
          json.dumps(files))
    s = score_hunk(files[0]["hunks"][0])
    check("mixed: ws=4", s["ws"] == 4, json.dumps(s))
    check("mixed: blank=1", s["blank"] == 1)
    check("mixed: signal=2", s["signal"] == 2)
    check("mixed: 50 < score <= 100", 50 < s["score"] <= 100)

    rot = (
        "diff --git a/rot.py b/rot.py\n"
        "--- a/rot.py\n"
        "+++ b/rot.py\n"
        "@@ -1,3 +1,3 @@\n"
        "-alpha\n"
        "-beta\n"
        "-gamma\n"
        "+gamma\n"
        "+alpha\n"
        "+beta\n"
    )
    s = score_hunk(parse_diff(rot)[0]["hunks"][0])
    check("rotate: identical>=4 (reorder detected)", s["identical"] >= 4, json.dumps(s))
    check("rotate: score>=50", s["score"] >= 50)

    real = (
        "diff --git a/x.py b/x.py\n"
        "--- a/x.py\n"
        "+++ b/x.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-old_func()\n"
        "+new_func()\n"
    )
    s = score_hunk(parse_diff(real)[0]["hunks"][0])
    check("real change: score=0 signal=2", s["score"] == 0.0 and s["signal"] == 2,
          json.dumps(s))

    check("empty input -> no files", parse_diff("") == [])
    print("selftest %s" % ("OK" if not failures else "FAILED: %s" % ", ".join(failures)))
    return 0 if not failures else 1


def main(argv=None):
    _utf8_stdio()
    ap = argparse.ArgumentParser(
        prog="diff-noise-score.py",
        description="计算 diff 中纯空白/重排类改动占比, 给本次变更打噪音分")
    ap.add_argument("input", nargs="?", help="diff 文件(缺省读 stdin)")
    ap.add_argument("--file", dest="file", help="同 positional, 二选一")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--fail-above", type=float, default=None, metavar="PCT",
                    help="噪音分超过 PCT 时退出码 1")
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

    files = parse_diff(text)
    per_file = []
    tot = {"changed": 0, "noise": 0, "ws": 0, "identical": 0, "blank": 0, "signal": 0}
    for f in files:
        agg = dict.fromkeys(tot, 0)
        for h in f["hunks"]:
            for k, v in score_hunk(h).items():
                if k != "score":
                    agg[k] += v
        agg["score"] = round(100.0 * agg["noise"] / agg["changed"], 1) if agg["changed"] else 0.0
        per_file.append(dict(file=f["file"], **agg))
        for k in tot:
            tot[k] += agg[k]
    overall = round(100.0 * tot["noise"] / tot["changed"], 1) if tot["changed"] else 0.0

    if args.json:
        print(json.dumps({"overall": dict(tot, score=overall, verdict=verdict(overall)),
                          "files": per_file}, ensure_ascii=False, indent=2))
    elif not per_file:
        print("(no hunks found / empty input)")
    else:
        for p in per_file:
            print("%-40s changed=%4d noise=%4d score=%5.1f%%  "
                  "[ws=%d identical=%d blank=%d signal=%d]"
                  % (p["file"][:40], p["changed"], p["noise"], p["score"],
                     p["ws"], p["identical"], p["blank"], p["signal"]))
        print("OVERALL: changed=%d noise=%d score=%.1f%% verdict=%s"
              % (tot["changed"], tot["noise"], overall, verdict(overall)))

    if args.fail_above is not None and overall > args.fail_above:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
