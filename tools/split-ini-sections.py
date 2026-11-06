#!/usr/bin/env python3
"""INI 按节拆分 / 合并工具。

把 INI 配置文件按 [section] 拆成多个 .ini 文件（每节一个，保留原始行，
含节内注释），也支持把一个目录下的多个 .ini 再合并回单个文件。

用法:
    python split-ini-sections.py split  config.ini  -o outdir/
    python split-ini-sections.py merge  outdir/     -o merged.ini

示例:
    python split-ini-sections.py split my.ini -o parts/
    python split-ini-sections.py merge parts/ -o rebuilt.ini

说明:
    - 首个 [section] 之前的行（文件头注释等）写入 parts/00__preamble__.ini。
    - split 会写清单文件 __order__.txt 记录节的原始顺序；merge 优先按
      清单顺序合并，可精确还原原文件（无清单时按文件名排序）。
    - 节名中的文件系统非法字符会被替换为 '_'，多个节重名时自动加序号。
只使用 Python 标准库。
"""

import argparse
import os
import re
import sys

PREAMBLE_NAME = "00__preamble__"
ORDER_MANIFEST = "__order__.txt"
_SECTION_RE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*(?:[;#].*)?$")
_ILLEGAL_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def parse_sections(text):
    """把 INI 文本解析为 [(section_name_or_None, [lines]), ...]，None 表示序言。"""
    groups = []
    current = (None, [])
    for line in text.splitlines():
        m = _SECTION_RE.match(line)
        if m:
            groups.append(current)
            current = (m.group("name").strip(), [line])
        else:
            current[1].append(line)
    groups.append(current)
    return groups


def _safe_filename(name, used):
    base = _ILLEGAL_FS.sub("_", name).strip().rstrip(".") or "unnamed"
    candidate, i = base, 1
    while candidate.lower() in used:
        i += 1
        candidate = "%s_%d" % (base, i)
    used[candidate.lower()] = True
    return candidate


def do_split(ini_path, outdir):
    with open(ini_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    os.makedirs(outdir, exist_ok=True)
    used = {}
    written = []
    for name, lines in parse_sections(text):
        if name is None:
            if not any(ln.strip() for ln in lines):
                continue
            fname = PREAMBLE_NAME + ".ini"
        else:
            fname = _safe_filename(name, used) + ".ini"
        path = os.path.join(outdir, fname)
        body = "\n".join(lines)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(body + ("\n" if body else ""))
        written.append((fname, name, len(lines)))
    # 写顺序清单，merge 时按此还原原始节顺序
    with open(os.path.join(outdir, ORDER_MANIFEST), "w",
              encoding="utf-8", newline="\n") as f:
        for fname, _, _ in written:
            f.write(fname + "\n")
    for fname, name, nlines in written:
        label = name if name is not None else "(preamble)"
        print("wrote %-40s section=%-30s lines=%d" % (fname, label, nlines))
    print("total: %d file(s) in %s" % (len(written), outdir))
    return 0


def do_merge(indir, out_path):
    if not os.path.isdir(indir):
        print("error: not a directory: %s" % indir, file=sys.stderr)
        return 2
    ini_names = sorted(
        n for n in os.listdir(indir)
        if n.lower().endswith(".ini") and os.path.isfile(os.path.join(indir, n))
    )
    if not ini_names:
        print("error: no .ini files in %s" % indir, file=sys.stderr)
        return 2
    # 有清单则按清单序还原原始节顺序
    manifest = os.path.join(indir, ORDER_MANIFEST)
    ordered = []
    if os.path.isfile(manifest):
        with open(manifest, "r", encoding="utf-8") as f:
            ordered = [ln.strip() for ln in f
                       if ln.strip() and os.path.isfile(os.path.join(indir, ln.strip()))]
        for n in ini_names:
            if n not in ordered:
                ordered.append(n)
    else:
        ordered = ini_names
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as out:
        for name in ordered:
            with open(os.path.join(indir, name), "r", encoding="utf-8",
                      errors="replace") as f:
                body = f.read()
            out.write(body)
            if body and not body.endswith("\n"):
                out.write("\n")
            print("merged: %s" % name)
    print("total: %d file(s) -> %s" % (len(ordered), out_path))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="INI 按节拆分（split）与合并（merge）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_split = sub.add_parser("split", help="把 INI 拆成每节一个文件")
    p_split.add_argument("ini", help="输入 INI 文件")
    p_split.add_argument("-o", "--outdir", required=True, help="输出目录")

    p_merge = sub.add_parser("merge", help="合并目录下所有 .ini 为一个文件")
    p_merge.add_argument("indir", help="包含 .ini 文件的目录")
    p_merge.add_argument("-o", "--out", required=True, help="输出 INI 文件")

    args = ap.parse_args(argv)
    if args.cmd == "split":
        return do_split(args.ini, args.outdir)
    return do_merge(args.indir, args.out)


if __name__ == "__main__":
    sys.exit(main())
