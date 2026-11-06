#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行数条形图 (loc-barchart) —— 在终端用 ASCII 条形图可视化各目录/文件的行数分布。

用途:
    递归扫描指定路径下的文本文件(自动跳过二进制文件与常见无关目录),
    统计每个文件的行数, 按目录(默认第一层)或按文件聚合,
    以 "目标 + 行数 + 占比 + ASCII 条形图" 的形式输出。

示例命令:
    python loc-barchart.py src/                        # 按 src 下第一层子目录统计
    python loc-barchart.py . --depth 2 --top 15        # 目录聚合两层, 只显示前 15 项
    python loc-barchart.py src --by-file --include "*.py"
    python loc-barchart.py . --exclude vendor --width 40
    python loc-barchart.py --self-test                 # 内置自测(临时目录 + 断言)

退出码:
    0 = 成功; 1 = 路径不存在或没有可统计的文本文件
"""

import argparse
import fnmatch
import json
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

# 默认跳过的目录名(对任意层级路径片段精确匹配)
DEFAULT_EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
    "dist", "build", "target", "coverage", ".cache",
}


def _force_utf8_stdout():
    """Windows 控制台下尽量把 stdio 切到 UTF-8, 避免中文乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _disp_width(s):
    """估算终端显示宽度: 东亚全角字符按 2 列计。"""
    return sum(2 if ord(c) > 0x2E7F else 1 for c in s)


def _pad(s, width):
    """左对齐补空格(按显示宽度)。"""
    return s + " " * max(0, width - _disp_width(s))


def _glob_match(text, globs):
    return any(fnmatch.fnmatch(text, g) for g in globs)


def count_lines(path):
    """返回文件行数; 二进制文件(前 8KB 含 NUL)返回 None。

    行数 = 文件内换行符个数; 若文件非空且末尾无换行, 再 +1。
    """
    try:
        if os.path.getsize(path) == 0:
            return 0
        with open(path, "rb") as f:
            head = f.read(8192)
            if b"\0" in head:
                return None
            f.seek(0)
            lines = 0
            last = b"\n"
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                lines += chunk.count(b"\n")
                last = chunk[-1:]
    except OSError:
        return None
    return lines + 1 if last != b"\n" else lines


def iter_files(root, include_globs, exclude_globs):
    """产出 (相对 posix 路径, 绝对路径)。目录按名字剪枝, 文件按 glob 过滤。"""
    if os.path.isfile(root):
        yield os.path.basename(root), root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        dirnames[:] = [
            d for d in dirnames
            if d not in DEFAULT_EXCLUDE_DIRS
            and not (exclude_globs and _glob_match(d, exclude_globs))
        ]
        for name in sorted(filenames):
            rel = name if rel_dir == "." else rel_dir + "/" + name
            if exclude_globs and (_glob_match(rel, exclude_globs) or _glob_match(name, exclude_globs)):
                continue
            if include_globs and not (_glob_match(rel, include_globs) or _glob_match(name, include_globs)):
                continue
            yield rel, os.path.join(dirpath, name)


def aggregate(root, args):
    """扫描并聚合。返回 (rows, total_lines, total_files, skipped_binary)。

    rows: 按 (行数降序, 名称) 排序的 [(key, lines, file_count)]
    """
    depth = max(1, args.depth)
    agg = {}
    skipped = 0
    for rel, abspath in iter_files(root, args.include, args.exclude):
        n = count_lines(abspath)
        if n is None:
            skipped += 1
            continue
        if args.by_file:
            key = rel
        else:
            parts = rel.split("/")
            key = "/".join(parts[:-1][:depth]) or "."
        item = agg.setdefault(key, [0, 0])
        item[0] += n
        item[1] += 1
    rows = [(k, v[0], v[1]) for k, v in agg.items()]
    rows.sort(key=lambda r: (-r[1], r[0]))
    total_lines = sum(r[1] for r in rows)
    total_files = sum(r[2] for r in rows)
    return rows, total_lines, total_files, skipped


def render(rows, total_lines, width=60, top=20):
    """渲染 ASCII 条形图, 返回多行字符串。"""
    shown = rows if top <= 0 else rows[:top]
    name_w = min(max([_disp_width(r[0]) for r in shown] + [4]), 46)
    max_v = max([r[1] for r in shown] + [1])
    width = max(10, width)
    out = ["{} {} {}  bar".format(_pad("目标", name_w), "lines".rjust(9), "pct".rjust(6)),
           "-" * (name_w + 21)]
    for key, lines, _nfiles in shown:
        pct = (lines / total_lines * 100) if total_lines else 0.0
        bar_n = int(round(width * lines / max_v)) if lines else 0
        if lines > 0 and bar_n == 0:
            bar_n = 1
        out.append("{} {} {}%  {}".format(
            _pad(key, name_w), "{:>9,}".format(lines), "{:>5.1f}".format(pct), "#" * bar_n))
    out.append("-" * (name_w + 21))
    out.append("合计 {} 项, {:,} 行".format(len(rows), total_lines))
    return "\n".join(out)


def run(args):
    if not os.path.exists(args.path):
        print("错误: 路径不存在: {}".format(args.path), file=sys.stderr)
        return 1
    rows, total_lines, total_files, skipped = aggregate(args.path, args)
    if not rows:
        print("没有找到可统计的文本文件。", file=sys.stderr)
        return 1
    if args.json:
        items = [{"name": k, "lines": v, "files": f,
                  "pct": round(v / total_lines * 100, 1) if total_lines else 0.0}
                 for k, v, f in rows]
        print(json.dumps({"total_lines": total_lines, "total_files": total_files,
                          "binary_skipped": skipped, "items": items},
                         ensure_ascii=False, indent=2))
    else:
        mode = "文件" if args.by_file else "目录, 深度 {}".format(max(1, args.depth))
        print("行数条形图: {}  (按{}聚合)".format(args.path, mode))
        print(render(rows, total_lines, width=args.width, top=args.top))
        if skipped:
            print("(已跳过 {} 个二进制文件)".format(skipped))
    return 0


def self_test():
    """构造临时示例目录, 验证聚合/过滤/二进制跳过与绘图输出。"""
    tmp = tempfile.mkdtemp(prefix="loc_barchart_test_")
    try:
        def w(rel, nlines):
            p = os.path.join(tmp, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write("line\n" * nlines)

        w("app.py", 12)
        w("core/engine.py", 30)
        w("core/util.py", 20)
        w("tests/test_app.py", 8)
        w("README.md", 5)
        w("empty.txt", 0)
        w(".git/should_skip.py", 99)  # 默认排除目录
        with open(os.path.join(tmp, "logo.bin"), "wb") as f:
            f.write(b"\0\1\2binary")  # 二进制文件

        a = SimpleNamespace(by_file=False, depth=1, include=[], exclude=[])
        rows, total_lines, total_files, skipped = aggregate(tmp, a)
        got = {k: v for k, v, _ in rows}
        expect = {".": 17, "core": 50, "tests": 8}  # '.': app.py 12 + README 5 + empty 0
        assert got == expect, "目录聚合不符: {} != {}".format(got, expect)
        assert (total_lines, total_files, skipped) == (75, 6, 1), (total_lines, total_files, skipped)

        a.by_file = True
        rows2, _, tf2, _ = aggregate(tmp, a)
        got2 = {k: v for k, v, _ in rows2}
        assert got2["core/engine.py"] == 30 and got2["tests/test_app.py"] == 8, got2
        assert tf2 == 6, tf2

        a.by_file = False
        a.include = ["*.py"]
        _, tl3, tf3, _ = aggregate(tmp, a)
        assert (tl3, tf3) == (70, 4), (tl3, tf3)  # 12+30+20+8

        print("[loc-barchart 自测] 聚合/过滤/二进制跳过 断言全部通过")
        print()
        print(render(rows, 75, width=40, top=10))
        print("SELF-TEST OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="loc-barchart",
        description="行数条形图: 在终端用 ASCII 条形图可视化各目录/文件的行数分布。",
        epilog="示例: python loc-barchart.py src/ --depth 2 --top 15")
    parser.add_argument("path", nargs="?", default=".", help="要统计的目录或单个文件(默认当前目录)")
    parser.add_argument("--by-file", action="store_true", help="按单个文件统计(默认按目录聚合)")
    parser.add_argument("--depth", type=int, default=1, help="目录聚合深度(默认 1)")
    parser.add_argument("--top", type=int, default=20, help="只显示前 N 项(默认 20, 0=全部)")
    parser.add_argument("--include", action="append", default=[], metavar="GLOB",
                        help="只统计匹配的文件, 可多次给出")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="额外排除的目录/文件名 glob, 可多次给出")
    parser.add_argument("--width", type=int, default=60, help="条形图最大宽度(默认 60)")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出统计结果")
    parser.add_argument("--self-test", action="store_true", help="运行内置自测")
    _force_utf8_stdout()
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
