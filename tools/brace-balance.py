#!/usr/bin/env python3
"""括号配平检查 / brace balance check.

逐文件统计花括号/圆括号/方括号的开闭数量, 并在跳过字符串与注释后做
配对检查, 报告不平衡的位置:
  * 多余的闭合括号、闭合类型与栈顶不匹配、文件结尾仍未闭合的括号;
  * 字符串直到文件结尾未闭合(其内括号不参与统计, 一并提示)。

语言特征按扩展名自动选择: Python(# 注释、三引号)、C/Java/Go/Rust 等
(// 与 /* */)、JS 系(额外含反引号)、CSS(仅 /* */)、SQL(--)、
JSON(仅字符串感知)、其余扩展名按朴素逐字符计数。
--naive 关闭全部字符串/注释感知, 一律朴素计数。

用法:
  python brace-balance.py PATH... [-r] [--ext .py,.js] [--exclude NAME]... [--naive] [-q]

示例:
  python brace-balance.py src -r                # 递归检查目录
  python brace-balance.py a.py b.js             # 检查指定文件
  python brace-balance.py src -r --naive        # 朴素计数, 不识别字符串/注释

退出码: 0 = 全部配平; 1 = 存在不平衡; 2 = 路径/IO 错误。
"""

import argparse
import os
import sys
from pathlib import Path

DEFAULT_EXCLUDES = {".git"}
MAX_SHOW = 10
PAIRS = {"(": ")", "[": "]", "{": "}"}
CLOSES = {v: k for k, v in PAIRS.items()}

# (行注释前缀, 块注释(开,闭)或 None, 字符串引号字符集, 是否支持三引号)
PROFILES = {
    "py":    (("#",), None, "'\"", True),
    "hash":  (("#",), None, "'\"", False),
    "c":     (("//",), ("/*", "*/"), "\"'", False),
    "js":    (("//",), ("/*", "*/"), "\"'`", False),
    "block": ((), ("/*", "*/"), "'\"", False),
    "sql":   (("--",), ("/*", "*/"), "'\"", False),
    "str":   ((), None, "'\"", False),
    "naive": ((), None, "", False),
}

EXT_PROFILE = {}
for _e in ".py .pyw".split():
    EXT_PROFILE[_e] = "py"
for _e in ".sh .bash .zsh .rb .yml .yaml .toml .ini .cfg .conf .properties .ps1".split():
    EXT_PROFILE[_e] = "hash"
for _e in ".c .h .cc .cpp .cxx .hpp .hh .hxx .java .cs .go .rs .swift .kt .kts .scala .dart .php .m .mm .vala .ino".split():
    EXT_PROFILE[_e] = "c"
for _e in ".js .jsx .ts .tsx .mjs .cjs .vue .less .scss".split():
    EXT_PROFILE[_e] = "js"
for _e in ".css".split():
    EXT_PROFILE[_e] = "block"
for _e in ".sql".split():
    EXT_PROFILE[_e] = "sql"
for _e in ".json .jsonc .geojson".split():
    EXT_PROFILE[_e] = "str"


def parse_exts(text):
    exts = set()
    for token in text.replace(",", " ").split():
        token = token.strip().lower()
        if token:
            exts.add("." + token.lstrip("."))
    return exts


def match_ext(path, exts):
    return True if exts is None else path.suffix.lower() in exts


def collect(roots, recursive, exts, excludes):
    """返回 (文件列表, 错误消息列表); 显式给出的文件不做扩展名过滤。"""
    files, errors = [], []
    for root in roots:
        p = Path(root)
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            if recursive:
                for dirpath, dirnames, filenames in os.walk(p):
                    dirnames[:] = sorted(d for d in dirnames if d not in excludes)
                    for name in sorted(filenames):
                        if name in excludes:
                            continue
                        f = Path(dirpath, name)
                        if match_ext(f, exts):
                            files.append(f)
            else:
                try:
                    names = sorted(os.listdir(p))
                except OSError as exc:
                    errors.append(f"{p}: {exc}")
                    continue
                for name in names:
                    if name in excludes:
                        continue
                    f = p / name
                    if f.is_file() and match_ext(f, exts):
                        files.append(f)
        else:
            errors.append(f"路径不存在: {p}")
    return files, errors


def decode_text(data):
    """宽 BOM 按对应编码解码; 其余按 UTF-8 容错解码; 二进制返回 None。"""
    if data[:4] in (b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff"):
        return data.decode("utf-32", errors="replace")
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    if b"\x00" in data[:8192]:
        return None
    return data.decode("utf-8-sig", errors="replace")


def scan_text(text, profile):
    """返回 (开闭计数 dict, 问题列表[(行, 列, 消息)]), 行列均从 1 起。"""
    line_c, block, quotes, allow_triple = profile
    counts = {c: 0 for c in "()[]{}"}
    stack, problems = [], []
    i, n = 0, len(text)
    line, col = 1, 1
    state = "code"
    str_ch, in_triple, str_start = "", False, (1, 1)

    def bump(seg):
        nonlocal line, col
        for c in seg:
            if c == "\n":
                line += 1
                col = 1
            else:
                col += 1

    while i < n:
        ch = text[i]
        if state == "code":
            lm = next((p for p in line_c if text.startswith(p, i)), None)
            if lm:
                state = "line_comment"
                i += len(lm)
                bump(lm)
                continue
            if block and text.startswith(block[0], i):
                state = "block_comment"
                i += len(block[0])
                bump(block[0])
                continue
            tri = next((q for q in quotes
                        if allow_triple and text.startswith(q * 3, i)), None)
            if tri:
                state = "string"
                str_ch, in_triple, str_start = tri, True, (line, col)
                i += 3
                bump(tri * 3)
                continue
            if ch in quotes:
                state = "string"
                str_ch, in_triple, str_start = ch, False, (line, col)
                i += 1
                bump(ch)
                continue
            if ch in counts:
                counts[ch] += 1
                if ch in PAIRS:
                    stack.append((ch, line, col))
                elif not stack:
                    problems.append((line, col, f"多余的闭合括号 “{ch}”"))
                else:
                    op, ol, oc = stack.pop()
                    if PAIRS[op] != ch:
                        problems.append((line, col,
                                         f"“{ch}” 与第 {ol} 行第 {oc} 列的 “{op}” 不匹配"))
                i += 1
                bump(ch)
                continue
            i += 1
            bump(ch)
            continue
        if state == "line_comment":
            if ch == "\n":
                state = "code"
            i += 1
            bump(ch)
            continue
        if state == "block_comment":
            if text.startswith(block[1], i):
                i += len(block[1])
                bump(block[1])
                state = "code"
                continue
            i += 1
            bump(ch)
            continue
        # state == "string"
        if ch == "\\" and i + 1 < n:
            seg = text[i:i + 2]
            i += 2
            bump(seg)
            continue
        if ch == str_ch:
            if in_triple:
                if text.startswith(str_ch * 3, i):
                    i += 3
                    bump(str_ch * 3)
                    state = "code"
                    continue
            else:
                state = "code"
                i += 1
                bump(ch)
                continue
        i += 1
        bump(ch)

    if state == "string":
        sl, sc = str_start
        problems.append((sl, sc, f"“{str_ch}” 字符串从此处直到文件结尾都未闭合"))
    for op, ol, oc in stack:
        problems.append((ol, oc, f"括号 “{op}” 未闭合"))
    problems.sort(key=lambda p: (p[0], p[1]))
    return counts, problems


def fmt_counts(counts):
    return "  ".join(f"{o} {counts[o]}/{counts[c]}"
                     for o, c in (("{", "}"), ("(", ")"), ("[", "]")))


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        description="逐文件统计括号开闭数量并检查配平, 报告不平衡位置")
    ap.add_argument("paths", nargs="+", metavar="PATH", help="文件或目录(可多个)")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="递归遍历目录(默认只看一层)")
    ap.add_argument("--ext", default="", metavar="EXTS",
                    help="只检查这些扩展名(逗号分隔, 覆盖默认代码扩展名集合); 显式给出的文件不受限")
    ap.add_argument("--exclude", action="append", default=[], metavar="NAME",
                    help="按名字跳过的目录或文件(可多次); 默认已跳过 .git")
    ap.add_argument("--naive", action="store_true",
                    help="朴素计数: 不识别字符串/注释中的括号")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="只显示不平衡的文件与汇总")
    args = ap.parse_args(argv)

    excludes = DEFAULT_EXCLUDES | set(args.exclude)
    exts = parse_exts(args.ext) if args.ext else set(EXT_PROFILE)
    files, errors = collect(args.paths, args.recursive, exts, excludes)

    n_ok = n_bad = n_skip = 0
    for f in files:
        try:
            data = f.read_bytes()
        except OSError as exc:
            errors.append(f"{f}: {exc}")
            continue
        text = decode_text(data)
        if text is None:
            n_skip += 1
            continue
        pname = "naive" if args.naive else EXT_PROFILE.get(f.suffix.lower(), "naive")
        counts, problems = scan_text(text, PROFILES[pname])
        if problems:
            n_bad += 1
            print(f"[不平衡] {f}  {fmt_counts(counts)}")
            for ln, cl, msg in problems[:MAX_SHOW]:
                print(f"    - 第 {ln} 行 第 {cl} 列: {msg}")
            if len(problems) > MAX_SHOW:
                print(f"    - …另外 {len(problems) - MAX_SHOW} 处未列出")
        else:
            n_ok += 1
            if not args.quiet:
                print(f"[配平]   {f}  {fmt_counts(counts)}")

    print(f"检查完成: 文本文件 {n_ok + n_bad} 个, 配平 {n_ok} 个, 不平衡 {n_bad} 个, "
          f"跳过二进制 {n_skip} 个 (计数格式: 开/闭)")
    if errors:
        print(f"发生 {len(errors)} 个错误:", file=sys.stderr)
        for msg in errors:
            print(f"  {msg}", file=sys.stderr)
        return 2
    return 1 if n_bad else 0


if __name__ == "__main__":
    sys.exit(main())
