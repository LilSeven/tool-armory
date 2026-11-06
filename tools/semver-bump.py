#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本号提升 (semver-bump)

从文件中定位第一个语义化版本号 (X.Y.Z)，按 major/minor/patch 提升后写回文件。
可选 --bump=all 将 major/minor/patch 同时提升。支持带 v 前缀的版本号（保留前缀）。

用法:
  python semver-bump.py FILE                 # 默认提升 patch
  python semver-bump.py FILE -b minor        # 提升 minor，patch 归零
  python semver-bump.py FILE -b major        # 提升 major，minor/patch 归零
  python semver-bump.py FILE -n              # 仅打印将写入的版本号，不写回
  python semver-bump.py FILE -o OUT          # 写到新文件而不覆盖原文件

示例:
  python semver-bump.py setup.py -b minor
"""
import argparse
import re
import sys

SEMVER_RE = re.compile(r"(?<![0-9A-Za-z_.-])(v|V)?(\d+)\.(\d+)\.(\d+)(?![0-9A-Za-z_.-])")


def bump(major: int, minor: int, patch: int, part: str):
    if part == "major":
        return major + 1, 0, 0
    if part == "minor":
        return major, minor + 1, 0
    return major, minor, patch + 1


def main() -> int:
    ap = argparse.ArgumentParser(description="定位文件中的语义化版本号并提升")
    ap.add_argument("file", help="目标文件")
    ap.add_argument("-b", "--bump", choices=["major", "minor", "patch"], default="patch")
    ap.add_argument("-n", "--dry-run", action="store_true", help="只显示结果不写回")
    ap.add_argument("-o", "--out", help="输出到指定文件")
    args = ap.parse_args()

    try:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"错误: 无法读取 {args.file}: {e}", file=sys.stderr)
        return 1

    m = SEMVER_RE.search(text)
    if not m:
        print("错误: 文件中未找到语义化版本号 (X.Y.Z)", file=sys.stderr)
        return 1

    major, minor, patch = int(m.group(2)), int(m.group(3)), int(m.group(4))
    n_major, n_minor, n_patch = bump(major, minor, patch, args.bump)
    new_ver = f"{m.group(1) or ''}{n_major}.{n_minor}.{n_patch}"
    new_text = text[: m.start()] + new_ver + text[m.end():]

    print(f"找到: {m.group(0)} -> 提升 {args.bump} -> {new_ver}")

    if args.dry_run:
        print("dry-run: 未写回")
        return 0

    out_path = args.out or args.file
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(new_text)
    except OSError as e:
        print(f"错误: 无法写入 {out_path}: {e}", file=sys.stderr)
        return 1
    print(f"已写入 {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
