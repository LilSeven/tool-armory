#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""高频变更报告 (churn-report) —— 解析 git log --numstat, 统计各文件被修改次数与累计改动行数。

用途:
    解析 `git log --numstat` 的文本输出, 按文件聚合:
      - 被修改次数(出现的 numstat 记录数, 重命名统计到新路径)
      - 累计新增 / 删除 / 总改动行数(二进制文件计次不计行)
    据此找出变更最频繁的"热点文件", 提示可重构或补测试的区域。

输入方式:
    管道:  git log --numstat | python churn-report.py
    文件:  python churn-report.py log.txt

示例命令:
    git log --numstat | python churn-report.py --top 20
    git log --numstat --since=2024-01-01 | python churn-report.py --min 3
    python churn-report.py log.txt --sort total --json
    python churn-report.py --self-test

退出码:
    0 = 成功; 1 = 输入中没有 numstat 记录; 2 = 参数错误
"""

import argparse
import json
import re
import sys

NUMSTAT_RE = re.compile(r"^(\d+|-)\t(\d+|-)\t(.*)$")
COMMIT_RE = re.compile(r"^(?:commit\s+[0-9a-f]{7,64}(?:\s.*)?|[0-9a-f]{7,64})\s*$")


def _force_utf8_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def unquote_git_path(p):
    """还原 git 的 C 风格引号路径。"""
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
    """重命名路径归一到新路径: "src/{a => b}/x.py" -> "src/b/x.py"。"""
    if " => " not in p:
        return p
    if "{" in p:
        i = p.index("{")
        k = p.find(" => ", i)
        j = p.find("}", k)
        if k != -1 and j != -1:
            return p[:i] + p[k + 4:j] + p[j + 1:]
    return p.split(" => ", 1)[1]


def parse_log(lines):
    """解析 git log --numstat 文本。

    返回 (stats, commits, entries):
      stats   = {path: {"times": n, "added": n, "deleted": n}}
      commits = 识别到的提交数(best effort, 依赖 commit 行/裸哈希行)
      entries = numstat 记录总数
    """
    stats = {}
    commits = 0
    entries = 0
    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        m = NUMSTAT_RE.match(line)
        if m:
            a, d = m.group(1), m.group(2)
            path = norm_rename(unquote_git_path(m.group(3)))
            st = stats.setdefault(path, {"times": 0, "added": 0, "deleted": 0})
            st["times"] += 1
            if a != "-":
                st["added"] += int(a)
            if d != "-":
                st["deleted"] += int(d)
            entries += 1
            continue
        if COMMIT_RE.match(line):
            commits += 1
    return stats, commits, entries


def sort_rows(stats, sort_key):
    rows = [dict(path=p, **v) for p, v in stats.items()]
    keys = {
        "times": lambda r: (-r["times"], -(r["added"] + r["deleted"]), r["path"]),
        "total": lambda r: (-(r["added"] + r["deleted"]), -r["times"], r["path"]),
        "added": lambda r: (-r["added"], -(r["added"] + r["deleted"]), r["path"]),
        "deleted": lambda r: (-r["deleted"], -(r["added"] + r["deleted"]), r["path"]),
        "name": lambda r: r["path"],
    }
    rows.sort(key=keys[sort_key])
    return rows


def render(rows, commits, total_added, total_deleted, top=20, min_times=1):
    shown = [r for r in rows if r["times"] >= min_times]
    shown = shown[:top] if top > 0 else shown
    out = ["git log --numstat 变更频率报告",
           "提交数: {}    涉及文件: {}    累计 +{}/-{}".format(
               commits, len(rows), total_added, total_deleted),
           "",
           "{} {} {} {} {}  {}".format("rank".rjust(5), "times".rjust(5),
                                       "add".rjust(7), "del".rjust(7),
                                       "total".rjust(7), "file"),
           "-" * 66]
    for i, r in enumerate(shown, 1):
        out.append("{} {} {} {} {}  {}".format(
            str(i).rjust(5), str(r["times"]).rjust(5),
            ("+" + str(r["added"])).rjust(7), ("-" + str(r["deleted"])).rjust(7),
            str(r["added"] + r["deleted"]).rjust(7), r["path"]))
    if not shown:
        out.append("(没有满足 --min 条件的文件)")
    out.append("-" * 66)
    return "\n".join(out)


def read_input(args, parser):
    if args.files:
        lines = []
        for fp in args.files:
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    lines.extend(f)
            except OSError as e:
                print("错误: 无法读取 {}: {}".format(fp, e), file=sys.stderr)
                sys.exit(1)
        return lines
    if not sys.stdin.isatty():
        return sys.stdin.read().splitlines()
    parser.error("缺少输入: 请提供文件参数或通过 stdin 管道传入 git log --numstat 输出")


def run(args, parser):
    lines = read_input(args, parser)
    stats, commits, entries = parse_log(lines)
    if entries == 0:
        print("错误: 输入中没有解析到任何 numstat 记录(期望 'git log --numstat' 的输出)。",
              file=sys.stderr)
        return 1
    total_added = sum(v["added"] for v in stats.values())
    total_deleted = sum(v["deleted"] for v in stats.values())
    rows = sort_rows(stats, args.sort)
    if args.json:
        print(json.dumps({
            "commits": commits, "entries": entries, "files": len(stats),
            "total_added": total_added, "total_deleted": total_deleted,
            "items": rows,
        }, ensure_ascii=False, indent=2))
    else:
        print(render(rows, commits, total_added, total_deleted,
                     top=args.top, min_times=args.min_times))
    return 0


def self_test():
    """用合成的 git log --numstat 文本验证解析与统计。"""
    sample = "\n".join([
        "commit {} (HEAD -> main)".format("a" * 40),
        "Author: Alice <alice@example.com>",
        "Date:   Mon Jan 1 10:00:00 2024 +0800",
        "",
        "    add feature",
        "",
        "5\t1\tsrc/main.py",
        "2\t0\tsrc/util.py",
        "",
        "commit " + "b" * 40,
        "Author: Bob <bob@example.com>",
        "Date:   Tue Jan 2 11:00:00 2024 +0800",
        "",
        "    refactor and rename",
        "",
        "3\t3\tsrc/main.py",
        "10\t0\tsrc/new.py",
        "1\t4\tsrc/{util => utils}/util.py",
        "-\t-\timg.png",
        "",
        "commit " + "c" * 40,
        "Author: Alice <alice@example.com>",
        "Date:   Wed Jan 3 09:00:00 2024 +0800",
        "",
        "    tweak main",
        "",
        "8\t2\tsrc/main.py",
        "1\t1\tREADME.md",
    ])
    stats, commits, entries = parse_log(sample.splitlines())
    assert commits == 3, commits
    assert entries == 8, entries  # 2 + 4 + 2 条 numstat 记录
    expect = {
        "src/main.py": {"times": 3, "added": 16, "deleted": 6},
        "src/util.py": {"times": 1, "added": 2, "deleted": 0},
        "src/utils/util.py": {"times": 1, "added": 1, "deleted": 4},
        "src/new.py": {"times": 1, "added": 10, "deleted": 0},
        "img.png": {"times": 1, "added": 0, "deleted": 0},  # 二进制: 计次不计行
        "README.md": {"times": 1, "added": 1, "deleted": 1},
    }
    assert stats == expect, stats

    rows = sort_rows(stats, "times")
    assert rows[0]["path"] == "src/main.py" and rows[0]["times"] == 3, rows[0]

    print("[churn-report 自测] numstat 解析/重命名归一/二进制 计数 断言全部通过")
    print()
    print(render(rows, commits, 30, 11, top=10, min_times=1))
    print()
    print("--min 2 过滤:")
    print(render(rows, commits, 30, 11, top=10, min_times=2))
    print("SELF-TEST OK")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="churn-report",
        description="高频变更报告: 解析 git log --numstat 统计各文件被修改次数与累计改动行数。",
        epilog="示例: git log --numstat | python churn-report.py --top 20")
    parser.add_argument("files", nargs="*", help="git log --numstat 输出文本(缺省读 stdin)")
    parser.add_argument("--top", type=int, default=20, help="只显示前 N 个文件(默认 20, 0=全部)")
    parser.add_argument("--min", dest="min_times", type=int, default=1,
                        help="只显示修改次数 >= N 的文件(默认 1)")
    parser.add_argument("--sort", choices=["times", "total", "added", "deleted", "name"],
                        default="times", help="排序依据(默认按修改次数)")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出全部统计")
    parser.add_argument("--self-test", action="store_true", help="运行内置自测")
    _force_utf8_stdout()
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    return run(args, parser)


if __name__ == "__main__":
    sys.exit(main())
