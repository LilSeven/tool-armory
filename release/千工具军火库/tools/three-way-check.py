#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""three-way-check.py — 三方合并预检

用途:
    给定 base 与两个分支(ours/theirs)各自相对 base 改动的行区间,
    按区间是否重叠预测合并时哪些文件可能产生冲突:
      - 区间相交                 -> conflict(很可能冲突)
      - 区间相距 <= --context    -> risky(邻近改动, 谨慎对待)
      - 其余                     -> clean
    也支持直接给 base/ours/theirs 三个目录, 用 difflib 自动计算行区间。

示例命令:
    python three-way-check.py --ranges ranges.json           # 区间文件, 格式见下
    cat ranges.json | python three-way-check.py --ranges -   # 从 stdin 读
    python three-way-check.py --base base/ --ours mine/ --theirs main/
    python three-way-check.py --ranges ranges.json --context 3 --json
    python three-way-check.py --ranges ranges.json --fail-on-conflict
    python three-way-check.py --selftest

ranges.json 格式(行号 1 起, 闭区间; [s, e] 且 s>e 表示在 s 行前的纯插入):
    {
      "src/app.py": {"ours": [[10, 20]], "theirs": [[15, 25]]},
      "src/util.py": {"ours": [[1, 2]],  "theirs": [[50, 60]]}
    }
单侧文件(--ours/--theirs)格式: {"src/app.py": [[10, 20]]}

退出码:
    0 = 完成预测(是否有冲突看输出)
    1 = 预测到冲突(仅当指定 --fail-on-conflict)
    2 = 用法或 IO 错误

说明:
    这是启发式预检: 区间数据可由 git diff -U0 的 @@ 头换算,
    默认 context=0 时仅"直接重叠"判 conflict, "紧邻(gap=0)"判 risky。
"""

import argparse
import difflib
import json
import os
import sys


def parse_range(r, path):
    if not (isinstance(r, (list, tuple)) and len(r) == 2):
        raise ValueError("bad range %r in %s (期望 [start, end])" % (r, path))
    s, e = int(r[0]), int(r[1])
    if s < 1:
        raise ValueError("range start < 1 in %s: %r" % (path, r))
    return (s, e)


def load_inline_ranges(obj):
    """解析 {path: {"ours": [[s,e]...], "theirs": [...]}} 结构。"""
    if not isinstance(obj, dict):
        raise ValueError("根节点应为 JSON 对象 {path: {ours: [...], theirs: [...]}}")
    data = {}
    for path, sides in obj.items():
        if not isinstance(sides, dict):
            raise ValueError('%s: 应为 {"ours": [...], "theirs": [...]}' % path)
        data[str(path)] = {
            "ours": [parse_range(r, path) for r in sides.get("ours", [])],
            "theirs": [parse_range(r, path) for r in sides.get("theirs", [])],
        }
    return data


def load_side_file(obj, side, data):
    """解析 {path: [[s,e],...]} 单侧区间文件, 合并进 data。"""
    if not isinstance(obj, dict):
        raise ValueError("%s 侧文件根节点应为 JSON 对象 {path: [[s,e],...]}" % side)
    for path, ranges in obj.items():
        entry = data.setdefault(str(path), {"ours": [], "theirs": []})
        entry[side].extend(parse_range(r, path) for r in ranges)
    return data


def ranges_conflict(a, b):
    """两个 base 行区间是否冲突(共享行, 或两侧在同一插入点插入)。

    区间为 1 起闭区间; [s, e] 且 s>e 表示第 s 行之前的零长度插入。
    """
    a1, a2 = a
    b1, b2 = b
    a_empty, b_empty = a2 < a1, b2 < b1
    if a_empty and b_empty:
        return a1 == b1
    if a_empty:
        return b1 <= a1 <= b2
    if b_empty:
        return a1 <= b1 <= a2
    return a1 <= b2 and b1 <= a2


def ranges_gap(a, b):
    """两区间之间未改动的 base 行数; 重叠返回 -1。"""
    a1, a2 = a
    b1, b2 = b
    if a2 < a1 and b2 < b1:
        return max(0, abs(a1 - b1) - 1)
    if a2 < a1:
        return max(0, b1 - a2 - 1)
    if b2 < b1:
        return max(0, a1 - b2 - 1)
    if b1 > a2:
        return b1 - a2 - 1
    if a1 > b2:
        return a1 - b2 - 1
    return -1


def evaluate_file(ours, theirs, context):
    """返回 (status, conflicts, risky)。"""
    conflicts, risky = [], []
    for a in ours:
        for b in theirs:
            if ranges_conflict(a, b):
                conflicts.append([list(a), list(b)])
            else:
                g = ranges_gap(a, b)
                if 0 <= g <= context:
                    risky.append({"ours": list(a), "theirs": list(b), "gap": g})
    if conflicts:
        return "conflict", conflicts, risky
    if risky:
        return "risky", [], risky
    return "clean", [], []


def changed_ranges(base_lines, side_lines):
    """用 difflib 计算 side 相对 base 的改动区间(base 行号, 1 起闭区间)。"""
    sm = difflib.SequenceMatcher(a=base_lines, b=side_lines, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if i2 > i1:
            out.append((i1 + 1, i2))
        else:
            out.append((i1 + 1, i1))  # 纯插入
    return out


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def read_lines(path):
    return read_text(path).splitlines()


def walk_files(root):
    """返回 {相对路径(用 /): 绝对路径}。"""
    files = {}
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace("\\", "/")
            files[rel] = full
    return files


def ranges_from_dirs(base_dir, ours_dir, theirs_dir):
    """三目录模式: 自动算出每个文件的 ours/theirs 改动区间。"""
    base, ours, theirs = walk_files(base_dir), walk_files(ours_dir), walk_files(theirs_dir)
    data = {}
    for rel in sorted(set(base) | set(ours) | set(theirs)):
        b = read_lines(base[rel]) if rel in base else None
        o = read_lines(ours[rel]) if rel in ours else None
        t = read_lines(theirs[rel]) if rel in theirs else None
        entry = {"ours": [], "theirs": [], "note": ""}
        if b is None:
            if o is not None and t is not None:
                entry["note"] = "added-on-both-sides"
                if o != t:                      # 两侧新增且内容不同 -> 必然冲突
                    entry["ours"], entry["theirs"] = [(1, 1)], [(1, 1)]
            elif o is not None:
                entry["note"] = "added-in-ours"
            elif t is not None:
                entry["note"] = "added-in-theirs"
            if entry["note"]:
                data[rel] = entry
            continue
        if o is None and t is None:
            continue                            # 两侧都没动这个文件
        if o is None:
            entry["ours"] = [(1, max(len(b), 1))]
            entry["note"] = "deleted-in-ours"
        else:
            entry["ours"] = changed_ranges(b, o)
        if t is None:
            entry["theirs"] = [(1, max(len(b), 1))]
            entry["note"] = (entry["note"] + "+" if entry["note"] else "") + "deleted-in-theirs"
        else:
            entry["theirs"] = changed_ranges(b, t)
        if entry["ours"] or entry["theirs"] or entry["note"]:
            data[rel] = entry
    return data


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

    # ---- 区间模式 ----
    data = load_inline_ranges({
        "overlap.py": {"ours": [[10, 20]], "theirs": [[15, 25]]},
        "apart.py": {"ours": [[1, 2]], "theirs": [[50, 60]]},
        "neighbor.py": {"ours": [[1, 5]], "theirs": [[7, 9]]},
    })
    st, c, _ = evaluate_file(data["overlap.py"]["ours"], data["overlap.py"]["theirs"], 0)
    check("overlap -> conflict", st == "conflict", json.dumps(c))
    st, _, _ = evaluate_file(data["apart.py"]["ours"], data["apart.py"]["theirs"], 0)
    check("apart -> clean", st == "clean")
    st, _, _ = evaluate_file(data["neighbor.py"]["ours"], data["neighbor.py"]["theirs"], 0)
    check("neighbor gap=1 -> clean at context=0", st == "clean")
    st, _, r = evaluate_file(data["neighbor.py"]["ours"], data["neighbor.py"]["theirs"], 1)
    check("neighbor gap=1 -> risky at context=1", st == "risky", json.dumps(r))

    # ---- 插入点语义 ----
    st, _, _ = evaluate_file([(3, 2)], [(3, 2)], 0)
    check("same insert point -> conflict", st == "conflict")
    st, _, _ = evaluate_file([(3, 2)], [(5, 6)], 0)
    check("insert elsewhere -> clean", st == "clean")
    st, _, _ = evaluate_file([(3, 2)], [(2, 4)], 0)
    check("insert inside modified region -> conflict", st == "conflict")

    # ---- 目录模式(difflib) ----
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "base")
        ours = os.path.join(td, "ours")
        theirs = os.path.join(td, "theirs")
        for d in (base, ours, theirs):
            os.makedirs(d)
        content_base = "".join("line%d\n" % i for i in range(1, 11))
        ours_clean = content_base.replace("line3\n", "LINE3\n").replace("line4\n", "LINE4\n")
        theirs_clean = content_base.replace("line6\n", "LINE6\n").replace("line7\n", "LINE7\n")
        ours_x = content_base.replace("line5\n", "OURS5\n")
        theirs_x = content_base.replace("line5\n", "THEIRS5\n")
        for d, c_clean, c_x in ((base, content_base, content_base),
                                (ours, ours_clean, ours_x),
                                (theirs, theirs_clean, theirs_x)):
            with open(os.path.join(d, "clean_case.py"), "w", encoding="utf-8", newline="\n") as f:
                f.write(c_clean)
            with open(os.path.join(d, "conf_case.py"), "w", encoding="utf-8", newline="\n") as f:
                f.write(c_x)
        data = ranges_from_dirs(base, ours, theirs)
        check("dirs: clean case detected",
              "clean_case.py" in data, json.dumps(sorted(data)))
        st, _, _ = evaluate_file(data["clean_case.py"]["ours"],
                                 data["clean_case.py"]["theirs"], 0)
        check("dirs: clean case -> clean", st == "clean",
              json.dumps(data["clean_case.py"]))
        st, _, _ = evaluate_file(data["conf_case.py"]["ours"],
                                 data["conf_case.py"]["theirs"], 0)
        check("dirs: conflict case -> conflict", st == "conflict",
              json.dumps(data["conf_case.py"]))

    print("selftest %s" % ("OK" if not failures else "FAILED: %s" % ", ".join(failures)))
    return 0 if not failures else 1


def main(argv=None):
    _utf8_stdio()
    ap = argparse.ArgumentParser(
        prog="three-way-check.py",
        description="三方合并预检: 基于 base 与两个分支的行区间重叠预测合并冲突")
    ap.add_argument("--ranges", help="区间 JSON 文件(格式见 docstring), '-' 表示 stdin")
    ap.add_argument("--ours", help="ours 侧区间 JSON {path: [[s,e],...]}")
    ap.add_argument("--theirs", help="theirs 侧区间 JSON {path: [[s,e],...]}")
    ap.add_argument("--base", help="base 目录; 与 --ours/--theirs 目录构成目录模式")
    ap.add_argument("--context", type=int, default=0,
                    help="区间间距 <= context 判为 risky(默认 0)")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--fail-on-conflict", action="store_true",
                    help="预测到 conflict 时退出码 1")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = ap.parse_args(argv)

    if args.selftest:
        return run_selftest()

    try:
        data = {}
        if args.base:
            if not (args.ours and args.theirs):
                print("error: --base 需要同时提供 --ours 与 --theirs 目录", file=sys.stderr)
                return 2
            data = ranges_from_dirs(args.base, args.ours, args.theirs)
        else:
            if args.ranges:
                raw = sys.stdin.read() if args.ranges == "-" else read_text(args.ranges)
                data = load_inline_ranges(json.loads(raw))
            if args.ours or args.theirs:
                if not (args.ours and args.theirs):
                    print("error: --ours 与 --theirs 需成对提供", file=sys.stderr)
                    return 2
                load_side_file(json.loads(read_text(args.ours)), "ours", data)
                load_side_file(json.loads(read_text(args.theirs)), "theirs", data)
            if not data:
                print("error: 需要 --ranges 或 --base/--ours/--theirs (见 -h)", file=sys.stderr)
                return 2
    except (ValueError, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    report = []
    counts = {"conflict": 0, "risky": 0, "clean": 0}
    for path in sorted(data):
        entry = data[path]
        status, conflicts, risky = evaluate_file(entry["ours"], entry["theirs"], args.context)
        counts[status] += 1
        report.append({"file": path, "status": status, "note": entry.get("note", ""),
                       "conflicts": conflicts, "risky": risky,
                       "ours": [list(x) for x in entry["ours"]],
                       "theirs": [list(x) for x in entry["theirs"]]})

    if args.json:
        print(json.dumps({"context": args.context, "counts": counts, "files": report},
                         ensure_ascii=False, indent=2))
    else:
        for r in report:
            line = "%-10s %s" % (r["status"].upper(), r["file"])
            if r["note"]:
                line += "  (%s)" % r["note"]
            print(line)
            for c in r["conflicts"]:
                print("    ours %d-%d x theirs %d-%d"
                      % (c[0][0], c[0][1], c[1][0], c[1][1]))
            for k in r["risky"]:
                print("    ours %d-%d ~ theirs %d-%d (gap=%d)"
                      % (k["ours"][0], k["ours"][1], k["theirs"][0], k["theirs"][1], k["gap"]))
        print("summary: %d file(s): %d conflict, %d risky, %d clean (context=%d)"
              % (len(report), counts["conflict"], counts["risky"], counts["clean"],
                 args.context))
    if args.fail_on_conflict and counts["conflict"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
