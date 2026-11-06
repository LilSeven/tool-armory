#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""search-result-save —— 搜索结果存档与差异对比。

执行一次模式扫描，把结果存为本地文本快照；下次扫描后可与快照做
统一差异对比（difflib），把“哪些位置出现了 TODO”之类的扫描结果
固化为基线并跟踪演进，也可直接当 CI 门禁（--diff 有差异时退出码 1）。

用法:
  扫描并打印:      python search-result-save.py PATTERN [路径...]
  存快照:          python search-result-save.py PATTERN src/ --save base
  与快照对比:      python search-result-save.py PATTERN src/ --diff base
  对比并更新快照:  python search-result-save.py PATTERN src/ --diff base --update
  查看快照:        python search-result-save.py --show base
  列出快照:        python search-result-save.py --list
  删除快照:        python search-result-save.py --delete base

说明:
  快照存放在 ./.search-snapshots/<tag>.txt（--dir 可改），头部以 "# "
  注释行记录元信息（标签/时间/模式等），对比时自动忽略头部，仅比较结果本体。
  目录会递归扫描，二进制文件（前 8KB 含 \\x00）自动跳过。

示例命令:
  python search-result-save.py "TODO|FIXME" src/ -i --save baseline
  python search-result-save.py "TODO|FIXME" src/ -i --diff baseline
  python search-result-save.py "TODO|FIXME" src/ -i --diff baseline --update
  python search-result-save.py -F "a.b(" logs/ --save today --dir D:/snaps

退出码: --diff: 0=无差异, 1=有差异, 2=出错或快照不存在；其余操作: 0=成功,
2=参数或 IO 错误。
仅用 Python 标准库。
"""

import argparse
import difflib
import fnmatch
import os
import re
import sys
from datetime import datetime
from pathlib import Path

_SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules"}


def sanitize_tag(tag):
    safe = re.sub(r"[^\w.-]+", "_", tag).strip("._")
    if not safe:
        raise SystemExit("错误: 无效的快照标签: %r" % tag)
    return safe


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


def compile_pattern(pat, fixed, ignore_case):
    p = re.escape(pat) if fixed else pat
    try:
        return re.compile(p, re.IGNORECASE if ignore_case else 0)
    except re.error as exc:
        raise SystemExit("错误: 正则无效 %r: %s" % (pat, exc))


def scan(pattern, roots, fixed, ignore_case, includes, encoding, force_text):
    """扫描并返回确定性排序的结果行列表 path:lineno:text。"""
    rx = compile_pattern(pattern, fixed, ignore_case)
    files, missing = collect_files(roots, includes)
    for p in missing:
        print("警告: 路径不存在，已跳过: %s" % p, file=sys.stderr)
    cwd = Path.cwd()
    seen = {}
    for fp in files:
        try:
            raw = fp.read_bytes()
        except OSError as exc:
            print("警告: 读取失败，已跳过 %s: %s" % (fp, exc), file=sys.stderr)
            continue
        if not force_text and b"\x00" in raw[:8192]:
            continue
        rel = Path(os.path.relpath(fp, cwd)).as_posix()
        for i, ln in enumerate(raw.decode(encoding, errors="replace").splitlines(), 1):
            if rx.search(ln):
                seen[(rel, i)] = "%s:%d:%s" % (rel, i, ln)
    return [seen[k] for k in sorted(seen)], missing


def snapshot_path(snap_dir, tag):
    return Path(snap_dir) / (sanitize_tag(tag) + ".txt")


def save_snapshot(snap_dir, tag, meta, body):
    snap_dir = Path(snap_dir)
    snap_dir.mkdir(parents=True, exist_ok=True)
    fp = snapshot_path(snap_dir, tag)
    lines = ["# snapshot: %s" % tag,
             "# created: %s" % datetime.now().isoformat(timespec="seconds"),
             "# pattern: %s" % meta["pattern"],
             "# flags: ignore_case=%s fixed=%s" % (meta["ignore_case"], meta["fixed"]),
             "# roots: %s" % " ".join(meta["roots"]),
             "# hits: %d" % len(body)]
    lines += body
    fp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return fp


def load_body(fp):
    """读快照，返回结果本体（忽略 "# " 头部注释行）。"""
    text = fp.read_text(encoding="utf-8")
    return [ln for ln in text.splitlines() if not ln.startswith("# ")]


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        prog="search-result-save",
        description="把一次扫描结果存为本地文本快照，可与下次结果对比差异。",
    )
    ap.add_argument("pattern", nargs="?", help="搜索模式（正则；-F 切换字面量）")
    ap.add_argument("paths", nargs="*", help="要扫描的文件或目录（默认当前目录）")
    ap.add_argument("--save", metavar="TAG", help="把本次结果存为快照 TAG")
    ap.add_argument("--diff", metavar="TAG", help="与快照 TAG 对比差异")
    ap.add_argument("--update", action="store_true",
                    help="与 --diff 连用：对比后把当前结果写入快照")
    ap.add_argument("--show", metavar="TAG", help="查看快照内容")
    ap.add_argument("--list", action="store_true", help="列出全部快照")
    ap.add_argument("--delete", metavar="TAG", help="删除快照 TAG")
    ap.add_argument("--dir", default=".search-snapshots",
                    help="快照目录（默认 ./.search-snapshots）")
    ap.add_argument("-i", "--ignore-case", action="store_true", help="忽略大小写")
    ap.add_argument("-F", "--fixed", action="store_true", help="按字面量匹配（不解释正则）")
    ap.add_argument("--include", action="append", default=[],
                    help="目录扫描时的文件名 glob 过滤，可多次")
    ap.add_argument("--encoding", default="utf-8", help="文件编码（默认 utf-8）")
    ap.add_argument("--text", action="store_true", help="不跳过二进制文件")
    args = ap.parse_args(argv)

    snap_dir = Path(args.dir)

    if args.list:
        if not snap_dir.is_dir():
            print("快照目录不存在: %s" % snap_dir)
            return 0
        for fp in sorted(snap_dir.glob("*.txt")):
            head = {ln.split(":", 1)[0]: ln.split(":", 1)[1].strip()
                    for ln in fp.read_text(encoding="utf-8").splitlines()[:6]
                    if ln.startswith("# ") and ":" in ln}
            print("%s\t%s\thits=%s\tpattern=%s"
                  % (fp.stem, head.get("# created", "?"),
                     head.get("# hits", "?"), head.get("# pattern", "?")))
        return 0

    if args.show:
        fp = snapshot_path(snap_dir, args.show)
        if not fp.is_file():
            print("错误: 快照不存在: %s" % fp, file=sys.stderr)
            return 2
        print(fp.read_text(encoding="utf-8"), end="")
        return 0

    if args.delete:
        fp = snapshot_path(snap_dir, args.delete)
        if not fp.is_file():
            print("错误: 快照不存在: %s" % fp, file=sys.stderr)
            return 2
        fp.unlink()
        print("已删除快照: %s" % fp)
        return 0

    if not args.pattern:
        ap.error("需要 PATTERN（或使用 --list / --show / --delete）")

    roots = args.paths or ["."]
    body, missing = scan(args.pattern, roots, args.fixed, args.ignore_case,
                         args.include, args.encoding, args.text)
    meta = {"pattern": args.pattern, "ignore_case": args.ignore_case,
            "fixed": args.fixed, "roots": roots}
    if not args.diff:
        for ln in body:
            print(ln)
        print("[共 %d 处命中]" % len(body), file=sys.stderr)

    if args.save:
        fp = save_snapshot(snap_dir, args.save, meta, body)
        print("快照已保存: %s（%d 条结果）" % (fp, len(body)))

    if args.diff:
        fp = snapshot_path(snap_dir, args.diff)
        if not fp.is_file():
            print("错误: 快照不存在: %s（先用 --save 创建）" % fp, file=sys.stderr)
            return 2
        old = load_body(fp)
        if old == body:
            print("与快照 %r 一致，无差异（%d 条结果）" % (args.diff, len(body)))
            rc = 0
        else:
            diff = difflib.unified_diff(old, body,
                                        fromfile="%s (快照)" % fp.name,
                                        tofile="当前扫描结果", lineterm="")
            print("\n".join(diff))
            print("[差异: 快照 %d 条 -> 当前 %d 条]" % (len(old), len(body)),
                  file=sys.stderr)
            rc = 1
        if args.update:
            save_snapshot(snap_dir, args.diff, meta, body)
            print("快照已更新: %s" % fp, file=sys.stderr)
        return rc

    if missing:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
