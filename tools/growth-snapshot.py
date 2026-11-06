#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""代码增长趋势（growth-snapshot）

用途：
    对目录做"快照"——统计其中各文本/代码文件的行数并保存为 JSON；
    可多次快照，然后任选两份快照对比，按目录汇总输出代码行数的
    增减趋势（净增行数与新增/删除/修改文件数）。

示例命令：
    python -I growth-snapshot.py snapshot ./proj -o snap1.json
    # ……修改代码后……
    python -I growth-snapshot.py snapshot ./proj -o snap2.json
    python -I growth-snapshot.py compare snap1.json snap2.json
    python -I growth-snapshot.py compare snap1.json snap2.json --depth 2 --top 20

子命令：
    snapshot  统计目录行数并保存快照 JSON
    compare   对比两份快照，按目录输出增减趋势

说明：行数按字节流中 \n 的个数计（末行无换行符也计 1 行）；
二进制文件（前 8KB 含 \0）自动跳过；默认只统计常见代码/文档
扩展名，可用 --ext 自定义（--ext '*' 表示全部文件）。
仅依赖 Python 标准库。
"""

import argparse
import datetime
import json
import os
import sys
import unicodedata

DEFAULT_EXCLUDES = {
    ".git", ".svn", ".hg", "__pycache__", "node_modules", "venv", ".venv",
    "dist", "build", ".idea", ".vscode", ".tox", ".mypy_cache",
}

DEFAULT_EXT_SPEC = (
    ".py,.pyw,.js,.mjs,.cjs,.ts,.tsx,.jsx,.java,.kt,.kts,.scala,.go,.rs,"
    ".c,.h,.cpp,.hpp,.cc,.cxx,.cs,.swift,.rb,.php,.pl,.lua,.dart,.groovy,"
    ".sh,.bash,.zsh,.ps1,.bat,.cmd,.sql,.html,.htm,.css,.scss,.less,.vue,"
    ".json,.yaml,.yml,.toml,.ini,.cfg,.conf,.xml,.md,.txt"
)


def _reconfigure_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _dw(s):
    """字符串显示宽度（全角字符记 2 列）。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
               for c in s)


def parse_exts(spec):
    """把 'a,b' 解析为扩展名集合；'*' 返回 None（不过滤）。"""
    spec = (spec or "").strip()
    if spec == "*":
        return None
    out = set()
    for e in spec.split(","):
        e = e.strip().lower()
        if e:
            out.add(e if e.startswith(".") else "." + e)
    return out


def iter_files(root, exts, excludes):
    """递归列出待统计文件；exts=None 表示不限扩展名。"""
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in excludes and not d.startswith(".")
        )
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            if exts is not None and os.path.splitext(fn)[1].lower() not in exts:
                continue
            yield os.path.join(dirpath, fn)


def count_lines(path):
    """统计文件行数（按 \n 计，末行无换行符也计 1 行）；二进制返回 None。"""
    with open(path, "rb") as f:
        first = f.read(8192)
        if b"\x00" in first:
            return None
        total = first.count(b"\n")
        last = first[-1:] if first else b""
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            total += chunk.count(b"\n")
            last = chunk[-1:]
    if first and last != b"\n":
        total += 1
    return total


def load_snapshot(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        print("错误：无法读取快照 %s：%s" % (path, exc), file=sys.stderr)
        return None
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        print("错误：不是有效的快照 JSON：%s" % path, file=sys.stderr)
        return None
    return data


def group_of(rel, depth):
    """把相对路径归到前 depth 级目录；根目录下的文件归入 (根目录)。"""
    dirs = rel.split("/")[:-1]
    if not dirs:
        return "(根目录)"
    return "/".join(dirs[:depth]) + "/"


def cmd_snapshot(args):
    root = args.dir
    if not os.path.isdir(root):
        print("错误：目录不存在：%s" % root, file=sys.stderr)
        return 2
    excludes = set(DEFAULT_EXCLUDES)
    excludes |= {x.strip() for x in args.exclude.split(",") if x.strip()}
    exts = None if args.all else parse_exts(args.ext)
    files = {}
    total = 0
    n_bin = 0
    for path in iter_files(root, exts, excludes):
        n = count_lines(path)
        if n is None:
            n_bin += 1
            continue
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        files[rel] = n
        total += n
    payload = {
        "tool": "growth-snapshot",
        "version": 1,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "root": os.path.abspath(root).replace(os.sep, "/"),
        "scope": "*" if args.all else args.ext,
        "files": files,
    }
    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=True)
    print("快照完成：%d 个文件，共 %d 行（跳过二进制 %d 个）-> %s"
          % (len(files), total, n_bin, args.output))
    return 0


def cmd_compare(args):
    sa = load_snapshot(args.a)
    sb = load_snapshot(args.b)
    if sa is None or sb is None:
        return 2
    fa, fb = sa["files"], sb["files"]
    depth = max(1, args.depth)

    groups = {}
    unchanged = 0
    for rel in set(fa) | set(fb):
        old, new = fa.get(rel), fb.get(rel)
        if old is not None and new is not None and old == new:
            unchanged += 1
        g = groups.setdefault(group_of(rel, depth),
                              {"old": 0, "new": 0, "add": 0, "del": 0, "mod": 0})
        if old is None:
            g["add"] += 1
            g["new"] += new
        elif new is None:
            g["del"] += 1
            g["old"] += old
        else:
            g["old"] += old
            g["new"] += new
            if old != new:
                g["mod"] += 1

    rows = [(name, g["old"], g["new"], g["new"] - g["old"],
             g["add"], g["del"], g["mod"])
            for name, g in groups.items()]
    if args.sort == "abs":
        rows.sort(key=lambda r: (-abs(r[3]), r[0]))
    elif args.sort == "name":
        rows.sort(key=lambda r: r[0])
    else:
        rows.sort(key=lambda r: (-r[3], r[0]))
    shown = rows if args.top <= 0 else rows[:args.top]

    def trend(d):
        return "↑" if d > 0 else ("↓" if d < 0 else "→")

    print("快照 A：%s（%s，%d 个文件，%d 行）"
          % (sa.get("root", "?"), sa.get("created", "?"),
             len(fa), sum(fa.values())))
    print("快照 B：%s（%s，%d 个文件，%d 行）"
          % (sb.get("root", "?"), sb.get("created", "?"),
             len(fb), sum(fb.values())))
    print("按前 %d 级目录汇总：" % depth)
    print()

    headers = ("目录", "旧行数", "新行数", "增减", "新增", "删除", "修改", "趋势")
    body = [(name, str(old), str(new), "%+d" % delta,
             str(add), str(dele), str(mod), trend(delta))
            for name, old, new, delta, add, dele, mod in shown]
    tot_old = sum(r[1] for r in rows)
    tot_new = sum(r[2] for r in rows)
    tot_delta = tot_new - tot_old
    total_row = ("合计", str(tot_old), str(tot_new), "%+d" % tot_delta,
                 str(sum(r[4] for r in rows)), str(sum(r[5] for r in rows)),
                 str(sum(r[6] for r in rows)), trend(tot_delta))

    widths = []
    for col, h in enumerate(headers):
        w = _dw(h)
        for r in body + [total_row]:
            w = max(w, _dw(r[col]))
        widths.append(w)
    right_cols = {1, 2, 3, 4, 5, 6}

    def fmt(cells):
        parts = []
        for col, cell in enumerate(cells):
            gap = max(widths[col] - _dw(cell), 0)
            parts.append(" " * gap + cell if col in right_cols else cell + " " * gap)
        return "  ".join(parts).rstrip()

    print(fmt(headers))
    for r in body:
        print(fmt(r))
    if body:
        print("-" * min(sum(widths) + 2 * (len(widths) - 1), 100))
    print(fmt(total_row))
    if unchanged:
        print()
        print("（另有 %d 个文件行数未变化）" % unchanged)
    return 0


def main(argv=None):
    _reconfigure_stdio()
    ap = argparse.ArgumentParser(
        prog="growth-snapshot", description="目录行数快照与代码增长趋势对比")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("snapshot", help="统计目录行数并保存快照 JSON")
    p1.add_argument("dir", help="要快照的目录")
    p1.add_argument("-o", "--output", required=True, help="快照输出 JSON 路径")
    p1.add_argument("--ext", default=DEFAULT_EXT_SPEC,
                    help="统计的扩展名（逗号分隔；'*'=全部文件）")
    p1.add_argument("--all", action="store_true",
                    help="统计全部文件（等价 --ext '*'）")
    p1.add_argument("--exclude", default="", help="额外排除的目录名（逗号分隔）")
    p1.set_defaults(func=cmd_snapshot)

    p2 = sub.add_parser("compare", help="对比两份快照，按目录输出增减趋势")
    p2.add_argument("a", help="较旧的快照 JSON")
    p2.add_argument("b", help="较新的快照 JSON")
    p2.add_argument("--depth", type=int, default=1,
                    help="按前 N 级目录汇总（默认 1）")
    p2.add_argument("--top", type=int, default=0, help="只显示前 N 行（0=全部）")
    p2.add_argument("--sort", choices=("delta", "abs", "name"), default="delta",
                    help="排序方式（默认 delta：按增减降序）")
    p2.set_defaults(func=cmd_compare)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
