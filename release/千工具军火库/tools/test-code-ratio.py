#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试代码占比 (test-code-ratio) —— 按路径规则区分测试与业务代码, 统计两者行数比例。

用途:
    递归扫描目录, 按路径规则把每个文本文件归入"测试代码"或"业务代码",
    统计两类各自的文件数、行数与占比, 并给出 测试:业务 行数比。

默认判定规则:
    1. 相对路径中任一"目录名"属于 test/tests/testing/spec/specs/__tests__/e2e → 测试代码
    2. 文件名匹配  test_*  /  *_test.*  /  *.test.*  /  *.spec.*  /  *_spec.*  /  conftest.py → 测试代码
    3. 其余为业务代码; 可用 --pattern 追加自定义 glob(同时匹配文件名与相对路径)

示例命令:
    python test-code-ratio.py .
    python test-code-ratio.py src --include "*.py" --include "*.js"
    python test-code-ratio.py . --pattern "*_spec.ts" --list
    python test-code-ratio.py . --json
    python test-code-ratio.py --self-test

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

DEFAULT_EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
    "dist", "build", "target", "coverage", ".cache",
}

TEST_DIR_NAMES = {"test", "tests", "testing", "spec", "specs", "__tests__", "e2e"}
TEST_BASE_PATTERNS = ["test_*", "*_test.*", "*.test.*", "*.spec.*", "*_spec.*", "conftest.py"]


def _force_utf8_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _disp_width(s):
    return sum(2 if ord(c) > 0x2E7F else 1 for c in s)


def _pad(s, width):
    return s + " " * max(0, width - _disp_width(s))


def _glob_match(text, globs):
    return any(fnmatch.fnmatch(text, g) for g in globs)


def count_lines(path):
    """返回文件行数; 二进制文件(前 8KB 含 NUL)返回 None。"""
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


def is_test_file(rel_posix, extra_patterns=()):
    """按路径规则判断是否测试代码。"""
    parts = rel_posix.split("/")
    if any(p.lower() in TEST_DIR_NAMES for p in parts[:-1]):
        return True
    base = parts[-1]
    if _glob_match(base, TEST_BASE_PATTERNS):
        return True
    return bool(extra_patterns) and (_glob_match(base, extra_patterns)
                                     or _glob_match(rel_posix, extra_patterns))


def scan(root, include_globs=(), exclude_globs=(), extra_patterns=()):
    """返回 (rows, skipped_binary); rows 为 [{path, test, lines}]。"""
    rows = []
    skipped = 0
    for rel, abspath in iter_files(root, include_globs, exclude_globs):
        n = count_lines(abspath)
        if n is None:
            skipped += 1
            continue
        rows.append({"path": rel, "test": is_test_file(rel, extra_patterns), "lines": n})
    return rows, skipped


def report(rows, root):
    """渲染汇总表, 返回字符串。"""
    test_rows = [r for r in rows if r["test"]]
    biz_rows = [r for r in rows if not r["test"]]
    t_lines = sum(r["lines"] for r in test_rows)
    b_lines = sum(r["lines"] for r in biz_rows)
    total = t_lines + b_lines

    def pct(x):
        return (x / total * 100) if total else 0.0

    out = ["路径: {}  (文本文件 {} 个)".format(root, len(rows)), "",
           "{}{}{}{}".format(_pad("类别", 10), "文件数".rjust(8), "行数".rjust(9), "占比".rjust(8)),
           "-" * 38,
           "{}{}{}{}%".format(_pad("测试代码", 10), str(len(test_rows)).rjust(8),
                              "{:>9,}".format(t_lines), "{:>7.1f}".format(pct(t_lines))),
           "{}{}{}{}%".format(_pad("业务代码", 10), str(len(biz_rows)).rjust(8),
                              "{:>9,}".format(b_lines), "{:>7.1f}".format(pct(b_lines))),
           "{}{}{}{}%".format(_pad("合计", 10), str(len(rows)).rjust(8),
                              "{:>9,}".format(total), "{:>7.1f}".format(100.0)),
           "",
           "测试:业务 行数比 = {}:{}".format(t_lines, b_lines),
           "测试占比 {}%".format(round(pct(t_lines), 1))]
    return "\n".join(out)


def run(args):
    if not os.path.exists(args.path):
        print("错误: 路径不存在: {}".format(args.path), file=sys.stderr)
        return 1
    rows, skipped = scan(args.path, args.include, args.exclude, args.pattern)
    if not rows:
        print("没有找到可统计的文本文件。", file=sys.stderr)
        return 1
    if args.json:
        t = [r for r in rows if r["test"]]
        b = [r for r in rows if not r["test"]]
        tl = sum(r["lines"] for r in t)
        bl = sum(r["lines"] for r in b)
        print(json.dumps({
            "test": {"files": len(t), "lines": tl},
            "business": {"files": len(b), "lines": bl},
            "total_lines": tl + bl,
            "ratio": "{}:{}".format(tl, bl),
            "binary_skipped": skipped,
            "files": rows,
        }, ensure_ascii=False, indent=2))
        return 0
    print(report(rows, args.path))
    if skipped:
        print("(已跳过 {} 个二进制文件)".format(skipped))
    if args.list:
        print()
        for r in sorted(rows, key=lambda r: r["path"]):
            tag = "[测试]" if r["test"] else "[业务]"
            print("{} {:>7,}  {}".format(tag, r["lines"], r["path"]))
    return 0


def self_test():
    """构造临时示例目录, 验证分类规则与统计断言。"""
    tmp = tempfile.mkdtemp(prefix="test_code_ratio_")
    try:
        def w(rel, nlines):
            p = os.path.join(tmp, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write("line\n" * nlines)

        w("src/main.py", 10)
        w("src/utils/helper.py", 20)
        w("README.md", 5)                 # 业务: 35 行
        w("tests/test_main.py", 15)
        w("tests/conftest.py", 5)
        w("app.test.js", 8)               # 测试: 28 行
        w(".git/hidden.py", 99)           # 排除目录
        with open(os.path.join(tmp, "img.bin"), "wb") as f:
            f.write(b"\0binary")

        rows, skipped = scan(tmp)
        test_map = {r["path"]: r["lines"] for r in rows if r["test"]}
        biz_map = {r["path"]: r["lines"] for r in rows if not r["test"]}
        assert test_map == {"tests/test_main.py": 15, "tests/conftest.py": 5,
                            "app.test.js": 8}, test_map
        assert biz_map == {"src/main.py": 10, "src/utils/helper.py": 20,
                           "README.md": 5}, biz_map
        assert skipped == 1, skipped

        # 目录名大小写不敏感: SPEC/ 目录(文件名不匹配任何测试模式)仅凭目录规则即判为测试
        # 注: 不能用 "Tests/", Windows 文件系统大小写不敏感, 会落进已存在的 tests/ 目录
        w("SPEC/helper.rb", 4)
        rows2, _ = scan(tmp)
        assert any(r["path"] == "SPEC/helper.rb" and r["test"] for r in rows2)

        # --pattern 追加规则
        w("spec_helper.rb", 6)
        rows3, _ = scan(tmp)
        assert not any(r["path"] == "spec_helper.rb" and r["test"] for r in rows3)
        rows4, _ = scan(tmp, extra_patterns=["spec_*.rb"])
        assert any(r["path"] == "spec_helper.rb" and r["test"] for r in rows4)

        print("[test-code-ratio 自测] 分类规则/排除目录/自定义 pattern 断言全部通过")
        print()
        print(report(rows2, tmp))
        print("SELF-TEST OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="test-code-ratio",
        description="测试代码占比: 按路径规则区分测试与业务代码, 统计两者行数比例。",
        epilog="示例: python test-code-ratio.py . --pattern \"*_spec.ts\" --list")
    parser.add_argument("path", nargs="?", default=".", help="要统计的目录或单个文件(默认当前目录)")
    parser.add_argument("--include", action="append", default=[], metavar="GLOB",
                        help="只统计匹配的文件, 可多次给出")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="额外排除的目录/文件名 glob, 可多次给出")
    parser.add_argument("--pattern", action="append", default=[], metavar="GLOB",
                        help="追加测试文件判定 glob(匹配文件名与相对路径), 可多次给出")
    parser.add_argument("--list", action="store_true", help="逐文件列出 [测试]/[业务] 分类")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出统计结果")
    parser.add_argument("--self-test", action="store_true", help="运行内置自测")
    _force_utf8_stdout()
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
