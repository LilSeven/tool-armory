#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi-pattern-grep —— 多模式 AND / OR / NOT 组合过滤搜索。

把多个模式按布尔逻辑组合后过滤行（或整个文件）：
  命中 = (所有 AND 模式都命中) 且 (若提供了 OR 模式，则至少命中一个)
         且 (不命中任何 NOT 模式)
只提供 OR 时即“任意命中”；AND 与 OR 可混用；NOT 永远做排除。

模式来源（均可多次、可混用）：
  -a/--and P     AND 模式：必须全部命中
  -o/--or P      OR 模式：至少命中一个
  -x/--not P     NOT 模式：命中任一即排除
  -e SPEC        带前缀的单参数写法，SPEC 形如 and:foo / or:bar / not:baz

默认按行过滤输出 path:行号:文本；--file-mode 时条件作用于整个文件
（AND/OR 对“文件中任一行”判定，NOT 要求全文件无命中），输出文件名。

示例命令:
  python multi-pattern-grep.py -a "def" -a "parse" src/          # 同时含 def 与 parse 的行
  python multi-pattern-grep.py -o "alpha" -o "beta" -x "test" .  # alpha 或 beta 且无 test
  python multi-pattern-grep.py -e "and:def" -e "not:TODO" src/ --file-mode
  python multi-pattern-grep.py -a "error" --count logs/          # 每文件命中计数

退出码: 0=有输出; 1=无输出; 2=参数或 IO 错误。
仅用 Python 标准库。
"""

import argparse
import fnmatch
import os
import re
import sys
from pathlib import Path

_SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules"}


def parse_specs(args):
    """归并各来源的模式，返回 [(op, pattern), ...]，op ∈ and/or/not。"""
    specs = []
    for v in (args.and_pats or []):
        specs.append(("and", v))
    for v in (args.or_pats or []):
        specs.append(("or", v))
    for v in (args.not_pats or []):
        specs.append(("not", v))
    for v in (args.specs or []):
        m = re.match(r"^(and|or|not)[:：](.+)$", v.strip(), re.IGNORECASE)
        if not m:
            raise SystemExit("错误: -e 参数需形如 and:PATTERN / or:PATTERN / "
                             "not:PATTERN，收到: %r" % v)
        specs.append((m.group(1).lower(), m.group(2)))
    if not any(op in ("and", "or") for op, _ in specs):
        raise SystemExit("错误: 至少需要一个 AND 或 OR 模式（-a/-o/-e），"
                         "单独的 NOT 模式没有过滤目标")
    return specs


def compile_specs(specs, fixed, ignore_case):
    flags = re.IGNORECASE if ignore_case else 0
    out = []
    for op, pat in specs:
        p = re.escape(pat) if fixed else pat
        try:
            out.append((op, re.compile(p, flags)))
        except re.error as exc:
            raise SystemExit("错误: 正则无效 %r: %s" % (pat, exc))
    return out


def line_predicate(compiled):
    ands = [c for op, c in compiled if op == "and"]
    ors = [c for op, c in compiled if op == "or"]
    nots = [c for op, c in compiled if op == "not"]

    def pred(line):
        if nots and any(c.search(line) for c in nots):
            return False
        if ands and not all(c.search(line) for c in ands):
            return False
        if ors and not any(c.search(line) for c in ors):
            return False
        return True

    return pred


def file_predicate(compiled):
    ands = [c for op, c in compiled if op == "and"]
    ors = [c for op, c in compiled if op == "or"]
    nots = [c for op, c in compiled if op == "not"]

    def pred(lines):
        if nots and any(c.search(ln) for c in nots for ln in lines):
            return False
        if ands and not all(any(c.search(ln) for ln in lines) for c in ands):
            return False
        if ors and not any(any(c.search(ln) for ln in lines) for c in ors):
            return False
        return True

    return pred


def include_match(fpath, includes):
    if not includes:
        return True
    name = fpath.name
    rel = fpath.as_posix()
    return any(fnmatch.fnmatch(name, g) or fnmatch.fnmatch(rel, g) for g in includes)


def collect_files(paths, includes):
    files, missing = [], []
    for p in paths:
        pp = Path(p)
        if pp.is_dir():
            for root, dirs, names in os.walk(pp):
                dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
                for f in sorted(names):
                    fp = Path(root) / f
                    if include_match(fp, includes):
                        files.append(fp)
        elif pp.is_file():
            files.append(pp)
        else:
            missing.append(p)
    return files, missing


def read_lines(fp, encoding, force_text):
    try:
        raw = Path(fp).read_bytes()
    except OSError as exc:
        print("警告: 读取失败，已跳过 %s: %s" % (fp, exc), file=sys.stderr)
        return None
    if not force_text and b"\x00" in raw[:8192]:
        return None
    return raw.decode(encoding, errors="replace").splitlines()


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        prog="multi-pattern-grep",
        description="多模式 AND/OR/NOT 组合过滤的增强版搜索工具。",
    )
    ap.add_argument("paths", nargs="+", help="文件或目录（目录递归扫描）")
    ap.add_argument("-a", "--and", dest="and_pats", action="append", metavar="P",
                    help="AND 模式：必须全部命中，可多次")
    ap.add_argument("-o", "--or", dest="or_pats", action="append", metavar="P",
                    help="OR 模式：至少命中一个，可多次")
    ap.add_argument("-x", "--not", dest="not_pats", action="append", metavar="P",
                    help="NOT 模式：命中任一即排除，可多次")
    ap.add_argument("-e", "--spec", dest="specs", action="append", metavar="SPEC",
                    help="带前缀模式 and:P / or:P / not:P，可多次")
    ap.add_argument("--file-mode", action="store_true",
                    help="条件作用于整个文件，命中时只输出文件名")
    ap.add_argument("-i", "--ignore-case", action="store_true", help="忽略大小写")
    ap.add_argument("-F", "--fixed", action="store_true", help="按字面量匹配（不解释正则）")
    ap.add_argument("-n", "--line-number", dest="line_number", action="store_true", default=True)
    ap.add_argument("--no-line-number", dest="line_number", action="store_false",
                    help="不显示行号")
    ap.add_argument("--no-filename", dest="with_filename", action="store_false", default=True,
                    help="不显示文件名前缀")
    ap.add_argument("--count", action="store_true", help="只输出每个文件的命中行数")
    ap.add_argument("-l", "--files-with-matches", action="store_true",
                    help="只列出命中的文件名")
    ap.add_argument("--include", action="append", default=[],
                    help="目录扫描时的文件名 glob 过滤，可多次")
    ap.add_argument("--encoding", default="utf-8", help="文件编码（默认 utf-8）")
    ap.add_argument("--text", action="store_true", help="不跳过二进制文件")
    args = ap.parse_args(argv)

    compiled = compile_specs(parse_specs(args), args.fixed, args.ignore_case)
    files, missing = collect_files(args.paths, args.include)
    for p in missing:
        print("警告: 路径不存在，已跳过: %s" % p, file=sys.stderr)

    pred_line = line_predicate(compiled)
    pred_file = file_predicate(compiled)
    hits = 0
    for fp in files:
        lines = read_lines(fp, args.encoding, args.text)
        if lines is None:
            continue
        label = fp.as_posix()
        if args.file_mode:
            if not pred_file(lines):
                continue
            hits += 1
            print(label)
            continue
        matched = [(i, ln) for i, ln in enumerate(lines) if pred_line(ln)]
        if not matched:
            continue
        hits += len(matched)
        if args.files_with_matches:
            print(label)
            continue
        if args.count:
            head = ("%s:" % label) if args.with_filename else ""
            print(head + str(len(matched)))
            continue
        for i, ln in matched:
            parts = []
            if args.with_filename:
                parts.append(label)
            if args.line_number:
                parts.append(str(i + 1))
            print(":".join(parts + [ln]) if parts else ln)

    if missing:
        return 2
    return 0 if hits else 1


if __name__ == "__main__":
    sys.exit(main())
