#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""大小写冲突检测 / case-conflict-finder

用途:
    递归扫描目录树, 找出"同一目录内仅大小写不同"的文件名/目录名对。
    这类名称在 Windows 默认(大小写不敏感)的访问方式下无法共存, 拷贝到
    大小写不敏感的盘/网盘/压缩包时会被覆盖或报错, 提前排查可避免事故。

    判定用 str.casefold()(比 lower 更稳, 能处理 ß 等特殊大小写)。
    注意: 即使目录被 fsutil 设为大小写敏感, 绝大多数 Windows 程序仍按
    大小写不敏感方式访问, 因此本工具一律视为冲突。

示例:
    python case-conflict-finder.py "K:\data"
    python case-conflict-finder.py "K:\data" --fail     # 发现冲突时退出码 1
    python case-conflict-finder.py "K:\data" --json

退出码: 0 = 扫描完成; 1 = 扫描完成且发现冲突(仅在 --fail 时);
        2 = 根目录无效或参数错误。
仅使用 Python 标准库; 输出为 UTF-8; 只读扫描, 不修改任何文件。
"""

import argparse
import json
import os
import sys


def setup_streams():
    """让 stdout/stderr 以 UTF-8 输出, 避免中文/特殊字符在 Windows 控制台报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def walk_tree(root, max_depth=None, errors=None, skipped=None):
    """先序遍历目录树, 逐条 yield (dirpath, name, is_dir, depth)。

    - 根的直接子项 depth=0; max_depth 限制下钻层数(None 不限);
    - 目录内条目按名称排序, 输出顺序确定;
    - 符号链接/目录联接不跟随; realpath 已访问过的目录跳过(防环);
    - 无权限等 OSError 记入 errors 列表后继续, 不中断整体扫描。
    """
    stack = [(root, 0)]
    seen = set()
    while stack:
        cur, depth = stack.pop()
        try:
            real = os.path.realpath(cur)
        except OSError:
            real = cur
        if real in seen:
            if skipped is not None:
                skipped.append(cur)
            continue
        seen.add(real)
        try:
            with os.scandir(cur) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as exc:
            if errors is not None:
                errors.append((cur, str(exc)))
            continue
        subdirs = []
        for ent in entries:
            try:
                is_dir = ent.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False
            yield cur, ent.name, is_dir, depth
            if is_dir and (max_depth is None or depth + 1 <= max_depth):
                subdirs.append((os.path.join(cur, ent.name), depth + 1))
        for sub in reversed(subdirs):
            stack.append(sub)


def find_conflicts_in(entries):
    """在单个目录的条目列表中找大小写冲突组。

    entries: [(name, is_dir), ...]
    返回: [[(name, "file"|"dir"), ...], ...] 仅含长度 > 1 的组, 组内按名称排序。
    """
    buckets = {}
    for name, is_dir in entries:
        buckets.setdefault(name.casefold(), []).append((name, "dir" if is_dir else "file"))
    groups = []
    for key in sorted(buckets):
        items = buckets[key]
        if len(items) > 1:
            groups.append(sorted(items))
    return groups


def main(argv=None):
    setup_streams()
    parser = argparse.ArgumentParser(
        prog="case-conflict-finder",
        description="找出同目录下仅大小写不同的文件名/目录名对。",
    )
    parser.add_argument("root", nargs="?", default=".",
                        help="要扫描的根目录 (默认: 当前目录)")
    parser.add_argument("--max-depth", type=int, default=None,
                        help="最多下钻层数(根的直接子项为第 1 层), 默认不限")
    parser.add_argument("--fail", action="store_true",
                        help="发现冲突时以退出码 1 结束(便于脚本/CI)")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"错误: 根目录不存在或不是目录: {root}", file=sys.stderr)
        return 2

    errors, skipped = [], []
    by_dir = {}
    n_files = n_dirs = 0
    for dirpath, name, is_dir, _depth in walk_tree(root, args.max_depth, errors, skipped):
        by_dir.setdefault(dirpath, []).append((name, is_dir))
        if is_dir:
            n_dirs += 1
        else:
            n_files += 1

    groups = []  # (dirpath, items)
    for dirpath in sorted(by_dir):
        for items in find_conflicts_in(by_dir[dirpath]):
            groups.append((dirpath, items))

    def rel_dir(d):
        return "." if d == root else os.path.relpath(d, root)

    if args.json:
        payload = {
            "root": root,
            "files": n_files,
            "dirs": n_dirs,
            "conflict_groups": len(groups),
            "conflict_items": sum(len(items) for _d, items in groups),
            "groups": [
                {"dir": rel_dir(d),
                 "items": [{"name": n, "type": t} for n, t in items]}
                for d, items in groups
            ],
            "errors": [{"path": p, "error": m} for p, m in errors],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"扫描根目录: {root}")
        print(f"条目统计: 文件 {n_files}, 目录 {n_dirs}")
        if groups:
            print(f"发现 {len(groups)} 组大小写冲突:")
            for d, items in groups:
                print(f"  目录: {rel_dir(d)}")
                for n, t in items:
                    kind = "目录" if t == "dir" else "文件"
                    print(f"    [{kind}] {n}")
            print("提示: 拷贝到大小写不敏感的文件系统/网盘前, 建议先重命名冲突项。")
        else:
            print("未发现大小写冲突")
        if errors:
            print(f"无法访问 {len(errors)} 处:")
            for p, msg in errors[:10]:
                print(f"  {p}: {msg}")

    if args.fail and groups:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
