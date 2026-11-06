#!/usr/bin/env python3
"""标记频次报表（marker-freq-report）——统计各类注解标记在仓库中的出现频次。

按整词统计 TODO / FIXME / HACK / XXX / NOTE / OPTIMIZE / BUG / REVIEW /
WORKAROUND 等标记在指定路径所有文本文件中的出现次数（默认区分大小写，
--ignore-case 可放宽），输出每个标记的总次数、涉及文件数与最集中的文件，
用于快速掌握仓库的"欠账地图"。按原始出现次数统计，不区分是否真在注释里。
仅依赖 Python 标准库。

用法:
    python marker-freq-report.py [路径...] [--markers TODO,FIXME] [--ignore-case] [--top-files N]

示例:
    python marker-freq-report.py src/ --markers TODO,FIXME,HACK --top-files 5

自测（构造临时示例文件）:
    python -I marker-freq-report.py --self-test
"""

from __future__ import annotations

import argparse
import os
import re
import sys

DEFAULT_MARKERS = ["TODO", "FIXME", "HACK", "XXX", "NOTE",
                   "OPTIMIZE", "BUG", "REVIEW", "WORKAROUND"]

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


def scan_freq(paths, markers, ignore_case=False):
    """返回 (标记 -> {"count": 次数, "files": {文件: 次数}}, 扫描的文本文件数)。"""
    flags = re.IGNORECASE if ignore_case else 0
    matchers = [(m, re.compile(r"\b%s\b" % re.escape(m), flags)) for m in markers]
    stats = {m: {"count": 0, "files": {}} for m in markers}
    nfiles = 0
    for path in iter_files(paths):
        lines = read_lines(path)
        if lines is None:
            continue
        nfiles += 1
        for name, rx in matchers:
            hits = sum(len(rx.findall(text)) for text in lines)
            if hits:
                stats[name]["count"] += hits
                stats[name]["files"][path] = stats[name]["files"].get(path, 0) + hits
    return stats, nfiles


def render(stats, nfiles, top_files=3):
    print("%-12s %6s %6s" % ("标记", "次数", "文件数"))
    ordered = sorted(stats.items(), key=lambda kv: (-kv[1]["count"], kv[0]))
    for name, info in ordered:
        print("%-12s %6d %6d" % (name, info["count"], len(info["files"])))
    print("---")
    print("扫描文本文件 %d 个" % nfiles)
    for name, info in ordered:
        if not info["files"]:
            continue
        tops = sorted(info["files"].items(), key=lambda kv: (-kv[1], kv[0]))[:top_files]
        detail = ", ".join("%s(%d)" % (p, c) for p, c in tops)
        print("  %s: %s" % (name, detail))


def self_test():
    """构造临时示例文件，断言频次统计精确（含大小写敏感与整词边界检查）。"""
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="marker-freq-")
    try:
        with open(os.path.join(tmp, "a.py"), "w", encoding="utf-8") as f:
            f.write("# TODO fix one\n"
                    "# TODO fix two\n"
                    "# FIXME alpha\n"
                    "x = 1  # FIXME beta FIXME gamma\n"
                    "# todo lowercase\n"
                    "# TODOS plural\n")
        with open(os.path.join(tmp, "b.js"), "w", encoding="utf-8") as f:
            f.write("// NOTE check me\n"
                    "// NOTE twice NOTE thrice\n"
                    "/* OPTIMIZE here */\n"
                    "// OPTIMIZE and BUG\n")
        markers = ["TODO", "FIXME", "NOTE", "OPTIMIZE", "BUG",
                   "HACK", "XXX", "REVIEW", "WORKAROUND"]
        stats, nfiles = scan_freq([tmp], markers)
        expect = {"TODO": 2, "FIXME": 3, "NOTE": 3, "OPTIMIZE": 2, "BUG": 1,
                  "HACK": 0, "XXX": 0, "REVIEW": 0, "WORKAROUND": 0}
        for m, want in expect.items():
            got = stats[m]["count"]
            assert got == want, "%s 期望 %d 次, 实际 %d" % (m, want, got)
        assert nfiles == 2, "应扫描 2 个文本文件, 实际 %d" % nfiles
        assert set(stats["TODO"]["files"]) == {os.path.join(tmp, "a.py")}, \
            "TODO 应只出现在 a.py"
        stats2, _ = scan_freq([tmp], ["TODO"], ignore_case=True)
        assert stats2["TODO"]["count"] == 3, "忽略大小写时 TODO 应为 3 次"
        render(stats, nfiles, top_files=3)
        print("频次断言全部通过（区分大小写、整词边界、--ignore-case 均符合预期）")
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
        description="标记频次报表：统计 TODO/FIXME/NOTE/OPTIMIZE 等注解标记的出现频次")
    parser.add_argument("paths", nargs="*", default=["."],
                        help="要扫描的文件或目录（默认当前目录）")
    parser.add_argument("--markers", default=",".join(DEFAULT_MARKERS),
                        help="逗号分隔的标记列表（默认 TODO,FIXME,HACK,XXX,NOTE,OPTIMIZE,BUG,REVIEW,WORKAROUND）")
    parser.add_argument("--ignore-case", action="store_true",
                        help="不区分大小写")
    parser.add_argument("--top-files", type=int, default=3, metavar="N",
                        help="每个标记最多列出的集中文件数（默认 3）")
    args = parser.parse_args(argv)
    markers = [m for m in re.split(r"[\s,]+", args.markers.strip()) if m]
    stats, nfiles = scan_freq(args.paths, markers, ignore_case=args.ignore_case)
    render(stats, nfiles, top_files=args.top_files)
    return 0


if __name__ == "__main__":
    sys.exit(main())
