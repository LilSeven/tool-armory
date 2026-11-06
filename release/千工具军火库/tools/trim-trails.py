#!/usr/bin/env python3
"""行尾空白修剪（trim-trails）——删除每行行尾的空格与制表符并统计改动行数。

功能：
  - 对给定文件或目录（--ext 过滤扩展名）中的文本文件逐行去掉行尾空白
  - 默认原地写回；--dry-run 只统计不写入
  - 报告每个文件的改动行数与总改动行数

用法示例：
  python trim-trails.py file.txt
  python trim-trails.py --dry-run file.txt other.txt
  python trim-trails.py --ext .txt,.md,.py somedir/

退出码：0 成功；1 有文件处理失败；2 参数错误。
"""
import argparse
import os
import re
import sys

def iter_target_files(paths, exts):
    for p in paths:
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for name in sorted(files):
                    if exts and not name.lower().endswith(exts):
                        continue
                    yield os.path.join(root, name)
        else:
            raise FileNotFoundError(p)

_EOL_RE = re.compile(r"(\r\n|\n|\r)\Z")

def trim_file(path, dry_run):
    changed = 0
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        text = f.read()
    out = []
    # splitlines(keepends=True) 按行切分并保留各自的行尾符（\r\n / \n / \r），
    # 因此混合换行的文件也能原样保留行尾符，只动空白。
    for ln in text.splitlines(True):
        m = _EOL_RE.search(ln)
        eol = m.group(1) if m else ""
        body = ln[: len(ln) - len(eol)]
        stripped = body.rstrip(" \t")
        if stripped != body:
            changed += 1
        out.append(stripped + eol)
    new_text = "".join(out)
    if not dry_run and changed:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
    return changed

def main(argv=None):
    p = argparse.ArgumentParser(description="删除每行行尾空格与制表符并统计改动行数，支持目录批处理")
    p.add_argument("paths", nargs="+", help="文件或目录（目录需配合 --ext 过滤或处理全部文件）")
    p.add_argument("--ext", default="", help="逗号分隔的扩展名过滤，如 .txt,.md")
    p.add_argument("--dry-run", action="store_true", help="只统计改动，不写回文件")
    args = p.parse_args(argv)

    exts = tuple(e.strip().lower() for e in args.ext.split(",") if e.strip()) or None
    total = 0
    files = 0
    errors = 0
    try:
        targets = list(iter_target_files(args.paths, exts))
    except FileNotFoundError as e:
        print(f"错误: 路径不存在: {e}", file=sys.stderr)
        return 1
    for path in targets:
        try:
            changed = trim_file(path, args.dry_run)
        except OSError as e:
            print(f"错误: {path}: {e}", file=sys.stderr)
            errors += 1
            continue
        files += 1
        total += changed
        print(f"{path}: 改动 {changed} 行" + ("（dry-run 未写入）" if args.dry_run else ""))
    print(f"合计: {files} 个文件，改动 {total} 行")
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main())
