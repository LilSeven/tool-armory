#!/usr/bin/env python3
"""目录差异比较：比较两个目录的文件差异（仅存在性或哈希级），输出新增/修改/缺失清单。

用法:
  python dir-diff.py <目录A> <目录B> [--hash] [--exclude "p1,p2"] [--out result.txt]

选项:
  --hash    哈希级比较（SHA-256）；缺省仅比较存在性与大小
  --exclude 逗号分隔的 fnmatch 通配符，跳过匹配的文件/目录
  --out     把报告写入文件（默认打印到 stdout）

输出三份清单:
  [仅A有] 只在目录A中存在
  [仅B有] 只在目录B中存在
  [内容不同] 两边都有但内容不同（--hash 时按哈希，否则按大小）

示例命令:
  python dir-diff.py D:/build1 D:/build2 --hash
  python dir-diff.py v1 v2 --exclude "*.log,.git" --out diff.txt
"""

import argparse
import fnmatch
import hashlib
import os
import sys


def excluded(rel: str, patterns) -> bool:
    rel = rel.replace(os.sep, "/")
    for p in patterns:
        p = p.strip().replace("\\", "/")
        if not p:
            continue
        if fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(os.path.basename(rel), p):
            return True
        if not p.endswith("*") and "/" not in p and f"{p}/" in rel + "/":
            return True
    return False


def walk_files(root: str, patterns):
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir != ".":
            dirnames[:] = [d for d in dirnames
                           if not excluded(os.path.join(rel_dir, d), patterns)]
        for fn in filenames:
            rel = fn if rel_dir == "." else os.path.join(rel_dir, fn)
            if excluded(rel, patterns):
                continue
            out[rel] = os.path.join(dirpath, fn)
    return out


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="比较两个目录的文件差异")
    ap.add_argument("dir_a", help="目录 A")
    ap.add_argument("dir_b", help="目录 B")
    ap.add_argument("--hash", action="store_true", help="哈希级比较(SHA-256)")
    ap.add_argument("--exclude", default="", help='排除通配符, 逗号分隔')
    ap.add_argument("--out", default="", help="报告输出文件路径")
    args = ap.parse_args(argv)

    a = os.path.abspath(args.dir_a)
    b = os.path.abspath(args.dir_b)
    for p in (a, b):
        if not os.path.isdir(p):
            print(f"错误: 目录不存在: {p}", file=sys.stderr)
            return 2

    patterns = [p for p in args.exclude.split(",") if p.strip()]
    files_a = walk_files(a, patterns)
    files_b = walk_files(b, patterns)

    only_a = sorted(set(files_a) - set(files_b))
    only_b = sorted(set(files_b) - set(files_a))

    diff = []
    for rel in sorted(set(files_a) & set(files_b)):
        sa, sb = os.path.getsize(files_a[rel]), os.path.getsize(files_b[rel])
        if args.hash:
            if sha256_file(files_a[rel]) != sha256_file(files_b[rel]):
                diff.append(rel)
        elif sa != sb:
            diff.append(rel)

    lines = [f"目录A: {a}", f"目录B: {b}",
             f"比较级别: {'哈希(SHA-256)' if args.hash else '存在性+大小'}", ""]
    lines.append(f"[仅A有] {len(only_a)} 个")
    lines += [f"  {r}" for r in only_a]
    lines.append(f"[仅B有] {len(only_b)} 个")
    lines += [f"  {r}" for r in only_b]
    lines.append(f"[内容不同] {len(diff)} 个")
    lines += [f"  {r}" for r in diff]
    report = "\n".join(lines)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")
        print(report)
        print(f"报告已写入: {args.out}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
