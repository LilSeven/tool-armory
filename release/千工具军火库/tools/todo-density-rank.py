#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TODO 密度排行 (todo-density-rank)。

用途:
    递归扫描目录(或指定文件), 统计代码中 TODO / FIXME 等标记出现的次数,
    计算"每千行代码标记数"(密度), 按密度降序排行, 定位技术债最集中的文件。
    默认大小写敏感、只统计 TODO; 默认只显示至少命中一次的文件。

示例命令:
    python todo-density-rank.py src/
    python todo-density-rank.py src/ app/ --tags TODO,FIXME --top 20
    python todo-density-rank.py . --ext py,js --ignore-case --show-zero
    python todo-density-rank.py --selftest

仅用 Python 标准库, 单文件; Windows / Git Bash 可用。
"""

import argparse
import os
import re
import sys

DEFAULT_EXTS = frozenset((
    ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".java", ".c", ".h",
    ".cc", ".cpp", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt",
    ".scala", ".sh", ".bash", ".ps1", ".lua", ".sql", ".html", ".css", ".scss",
    ".vue", ".yaml", ".yml", ".json", ".md", ".toml", ".ini",
))
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", "dist", "build", ".idea", ".vscode", "target",
}


def iter_files(paths, exts, include_all):
    """产出 (绝对路径, 展示路径)。显式指定的文件不受扩展名过滤限制。"""
    seen = set()
    for p in paths:
        if os.path.isfile(p):
            rp = os.path.abspath(p)
            if rp not in seen:
                seen.add(rp)
                yield rp, p
        elif os.path.isdir(p):
            for dirpath, dirnames, filenames in os.walk(p):
                dirnames[:] = sorted(
                    d for d in dirnames
                    if d not in SKIP_DIRS and not d.startswith("."))
                for fn in sorted(filenames):
                    full = os.path.join(dirpath, fn)
                    if not include_all and exts is not None:
                        if os.path.splitext(fn)[1].lower() not in exts:
                            continue
                    rp = os.path.abspath(full)
                    if rp not in seen:
                        seen.add(rp)
                        yield rp, full.replace("\\", "/")
        else:
            print(f"警告: 路径不存在, 跳过: {p}", file=sys.stderr)


def build_regex(tags, ignore_case):
    pat = r"\b(?:" + "|".join(re.escape(t) for t in tags) + r")\b"
    return re.compile(pat, re.IGNORECASE if ignore_case else 0)


def analyze_file(path, regex):
    """返回 (命中数, 行数); 二进制/不可读返回 None。"""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if b"\x00" in data:
        return None                      # 二进制文件
    text = data.decode("utf-8", errors="replace")
    nlines = len(text.splitlines())
    count = len(regex.findall(text))
    return count, nlines


def scan(paths, tags, ignore_case, exts, min_lines=1, show_zero=False,
         include_all=False):
    """返回 [(密度, 命中数, 行数, 展示路径), ...] 按密度降序。"""
    regex = build_regex(tags, ignore_case)
    rows = []
    for rp, disp in iter_files(paths, exts, include_all):
        res = analyze_file(rp, regex)
        if res is None:
            continue
        count, nlines = res
        if nlines < min_lines:
            continue
        if count == 0 and not show_zero:
            continue
        density = count * 1000.0 / nlines
        rows.append((density, count, nlines, disp))
    rows.sort(key=lambda r: (-r[0], -r[1], r[3]))
    return rows


def _setup_stdio():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        def put(name, lines):
            with open(os.path.join(td, name), "w", encoding="utf-8",
                      newline="\n") as f:
                f.write("\n".join(lines) + "\n")

        put("a.py", ["import os"] + [f"x{i} = {i}" for i in range(97)] +
            ["# TODO refactor a", "# TODO cleanup a"])          # 100 行 2 个
        put("b.js", ["// TODO fix b"] + [f"var y{i} = {i};" for i in range(9)])
                                                                    # 10 行 1 个
        put("c.md", ["# doc"] + ["todo lowercase word"] * 28 + ["# end"])
                                                                    # 小写, 默认不计
        put("d.py", [f"def f{i}(): pass" for i in range(39)] +
            ["# FIXME soon d"])                                     # 40 行 FIXME 1 个

        rows = scan([td], ("TODO",), False, DEFAULT_EXTS)
        names = [os.path.basename(r[3]) for r in rows]
        assert names == ["b.js", "a.py"], names
        assert abs(rows[0][0] - 100.0) < 1e-9 and abs(rows[1][0] - 20.0) < 1e-9, rows

        rows2 = scan([td], ("TODO", "FIXME"), False, DEFAULT_EXTS)
        names2 = [os.path.basename(r[3]) for r in rows2]
        assert names2 == ["b.js", "d.py", "a.py"], names2
        assert abs(rows2[1][0] - 25.0) < 1e-9, rows2

        rows3 = scan([td], ("TODO",), False, (".py",))
        assert [os.path.basename(r[3]) for r in rows3] == ["a.py"], rows3
    print("selftest PASS: 密度计算(100/25/20 每千行)、多标签、扩展名过滤、"
          "大小写敏感、排行顺序均正确")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="todo-density-rank",
        description="统计每千行代码中的 TODO 数量, 按密度排行")
    ap.add_argument("paths", nargs="*", default=["."],
                    help="要扫描的文件或目录 (缺省当前目录)")
    ap.add_argument("--tags", default="TODO",
                    help="逗号分隔的标记, 默认 TODO (如 TODO,FIXME,HACK)")
    ap.add_argument("--ext", default="",
                    help="逗号分隔的扩展名过滤 (如 py,js; 缺省用内置代码扩展名)")
    ap.add_argument("--all", action="store_true",
                    help="扫描所有非二进制文件(忽略扩展名过滤)")
    ap.add_argument("--ignore-case", action="store_true",
                    help="标记匹配忽略大小写")
    ap.add_argument("--top", type=int, default=0, help="只显示前 N 名 (0=全部)")
    ap.add_argument("--min-lines", type=int, default=1,
                    help="文件最少行数, 低于则不计密度 (默认 1)")
    ap.add_argument("--show-zero", action="store_true",
                    help="也显示没有任何标记的文件")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = ap.parse_args(argv)
    _setup_stdio()
    if args.selftest:
        return selftest()

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    if not tags:
        ap.error("--tags 不能为空")
    if args.all:
        exts = None
    elif args.ext:
        exts = frozenset(
            e if e.startswith(".") else "." + e
            for e in (x.strip().lower() for x in args.ext.split(",")) if e)
    else:
        exts = DEFAULT_EXTS

    rows = scan(args.paths, tags, args.ignore_case, exts,
                min_lines=args.min_lines, show_zero=args.show_zero,
                include_all=args.all)
    skipped_note = "" if args.show_zero else "(默认不显示 0 命中文件)"
    print(f"TODO 密度排行 (个/千行代码) | tags={','.join(tags)}"
          + (" | 忽略大小写" if args.ignore_case else ""))
    print(f"入榜文件 {len(rows)} 个 {skipped_note}")
    if not rows:
        print("(无符合条件的数据)")
        return 0
    if args.top > 0:
        rows = rows[:args.top]
    print(f"{'排名':>4}  {'密度':>10}  {'数量':>4}  {'行数':>8}  文件")
    for i, (density, count, nlines, disp) in enumerate(rows, 1):
        print(f"{i:>4}  {density:>10.2f}  {count:>4}  {nlines:>8}  {disp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
