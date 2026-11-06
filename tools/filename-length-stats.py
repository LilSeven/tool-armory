#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""文件名长度统计 / filename-length-stats

用途:
    递归统计目录树内所有文件名与目录名的字符长度分布(直方图), 列出
    最长的名称, 并按目录聚合标出"过长命名的重灾区"(长名条目最集中的
    目录); 同时按 Windows MAX_PATH(默认 260 字符)预警完整路径过长的条目。

示例:
    python filename-length-stats.py "K:\data"
    python filename-length-stats.py "K:\data" --threshold 60 --bucket 8 --top 5 --worst 5
    python filename-length-stats.py "K:\data" --json

说明:
    - 长度按字符数计(不是字节), 对应 NTFS 的 255 字符单名上限;
    - 只读扫描, 不修改任何文件; 无权限的目录会计入"无法访问"并继续;
    - 符号链接/目录联接不展开(另有 realpath 防环), 避免死循环;
    - 结果在内存中汇总, 超大目录树请配合 --max-depth 分区扫描。

退出码: 0 = 扫描完成(无论是否发现长名); 2 = 根目录无效或参数错误。
仅使用 Python 标准库; 输出为 UTF-8。
"""

import argparse
import json
import os
import sys

DEFAULT_THRESHOLD = 80    # "长名"阈值: 名称字符数 >= 该值
DEFAULT_BUCKET = 10       # 直方图桶宽(字符)
DEFAULT_PATH_LIMIT = 260  # Windows MAX_PATH
BAR_WIDTH = 40


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


def main(argv=None):
    setup_streams()
    parser = argparse.ArgumentParser(
        prog="filename-length-stats",
        description="统计文件名/目录名的字符长度分布, 标出过长命名的重灾区。",
    )
    parser.add_argument("root", nargs="?", default=".",
                        help="要扫描的根目录 (默认: 当前目录)")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help="长名阈值(字符), 默认 %(default)s")
    parser.add_argument("--bucket", type=int, default=DEFAULT_BUCKET,
                        help="直方图桶宽(字符), 默认 %(default)s")
    parser.add_argument("--top", type=int, default=10,
                        help="最长名称列表条数, 默认 %(default)s")
    parser.add_argument("--worst", type=int, default=10,
                        help="重灾区目录数上限, 默认 %(default)s")
    parser.add_argument("--path-limit", type=int, default=DEFAULT_PATH_LIMIT,
                        help="完整路径长度预警阈值(字符), 默认 %(default)s")
    parser.add_argument("--max-depth", type=int, default=None,
                        help="最多下钻层数(根的直接子项为第 1 层), 默认不限")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)

    if (args.threshold < 1 or args.bucket < 1 or args.path_limit < 1
            or args.top < 0 or args.worst < 0):
        parser.error("--threshold/--bucket/--path-limit 须 >= 1, --top/--worst 须 >= 0")

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"错误: 根目录不存在或不是目录: {root}", file=sys.stderr)
        return 2

    errors, skipped = [], []
    n_files = n_dirs = 0
    lengths = []        # (长度, 相对路径, 是否目录)
    long_by_dir = {}    # 目录 -> [长名条目数, 最长长度]
    path_warnings = []  # (完整路径长度, 相对路径)

    for dirpath, name, is_dir, _depth in walk_tree(root, args.max_depth, errors, skipped):
        length = len(name)
        if is_dir:
            n_dirs += 1
        else:
            n_files += 1
        rel = os.path.relpath(os.path.join(dirpath, name), root)
        lengths.append((length, rel, is_dir))
        if length >= args.threshold:
            agg = long_by_dir.setdefault(dirpath, [0, 0])
            agg[0] += 1
            agg[1] = max(agg[1], length)
        abs_length = len(os.path.join(dirpath, name))
        if abs_length >= args.path_limit:
            path_warnings.append((abs_length, rel))

    total = n_files + n_dirs

    # 直方图
    histo = {}
    for length, _rel, _is_dir in lengths:
        lo = (length - 1) // args.bucket * args.bucket + 1
        key = (lo, lo + args.bucket - 1)
        histo[key] = histo.get(key, 0) + 1
    histo_sorted = sorted(histo.items())
    max_count = max(histo.values(), default=0)

    longest = sorted(lengths, key=lambda t: (-t[0], t[1]))[: args.top]
    hotspots = sorted(long_by_dir.items(),
                      key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))[: args.worst]
    path_warnings.sort(key=lambda t: (-t[0], t[1]))

    def rel_dir(d):
        return "." if d == root else os.path.relpath(d, root)

    if args.json:
        payload = {
            "root": root,
            "files": n_files,
            "dirs": n_dirs,
            "threshold": args.threshold,
            "bucket": args.bucket,
            "path_limit": args.path_limit,
            "histogram": [{"min": lo, "max": hi, "count": c}
                          for (lo, hi), c in histo_sorted],
            "longest": [{"length": l, "type": "dir" if d else "file", "path": r}
                        for l, r, d in longest],
            "hotspots": [{"dir": rel_dir(d), "long_count": c, "max_length": m}
                         for d, (c, m) in hotspots],
            "path_warnings": {
                "limit": args.path_limit,
                "count": len(path_warnings),
                "samples": [{"length": l, "path": r} for l, r in path_warnings[:10]],
            },
            "errors": [{"path": p, "error": m} for p, m in errors],
            "skipped_cycles": [rel_dir(p) for p in skipped],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"扫描根目录: {root}")
    print(f"条目统计: 文件 {n_files}, 目录 {n_dirs} (共 {total})")
    print()
    print(f"名称长度分布 (单位: 字符, 桶宽 {args.bucket}):")
    if histo_sorted:
        for (lo, hi), cnt in histo_sorted:
            bar = "#" * max(1, round(cnt / max_count * BAR_WIDTH))
            pct = cnt / total * 100 if total else 0.0
            print(f"  {lo:>5}-{hi:<5}: {cnt:>6} ({pct:5.1f}%) {bar}")
    else:
        print("  (无条目)")
    print()
    if longest:
        print(f"最长名称 Top {len(longest)}:")
        for length, rel, is_dir in longest:
            kind = "目录" if is_dir else "文件"
            print(f"  {length:>4} [{kind}] {rel}")
    else:
        print("最长名称: (无条目)")
    print()
    if hotspots:
        print(f"重灾区 (名称长度 >= {args.threshold} 字符, 按长名条目数排序, 最多 {args.worst} 个):")
        for d, (c, m) in hotspots:
            print(f"  长名 {c:>4} 个, 最长 {m:>4}: {rel_dir(d)}")
    else:
        print(f"重灾区: 未发现名称长度 >= {args.threshold} 字符的条目")
    print()
    if path_warnings:
        print(f"路径长度预警 (完整路径 >= {args.path_limit} 字符): 共 {len(path_warnings)} 条, 最多显示 10 条:")
        for length, rel in path_warnings[:10]:
            print(f"  {length:>4}  {rel}")
    else:
        print(f"路径长度预警 (完整路径 >= {args.path_limit} 字符): 0 条")
    if errors or skipped:
        print(f"无法访问 {len(errors)} 处; 跳过重复/环形目录 {len(skipped)} 处:")
        for p, msg in errors[:10]:
            print(f"  {p}: {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
