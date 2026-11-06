#!/usr/bin/env python3
r"""目录深度统计器（depth-stats）

用途:
    递归统计目录树的最大深度与各深度层的文件/目录数量分布，并列出
    深度超过阈值的路径，帮助定位嵌套过深、难以维护的目录结构。
    深度定义: 根目录本身为第 0 层，根下直接条目为第 1 层，依此类推。

示例命令:
    python depth-stats.py K:\data
    python depth-stats.py K:\data --max-depth 4 --limit 50
    python depth-stats.py K:\data --json

退出码:
    0 = 正常完成（发现过深路径也算正常）
    2 = 参数错误或目录不存在
"""

import argparse
import json
import os
import sys
from collections import Counter


def _safe_stdout():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass


def scan(root, threshold):
    """返回 (files_at, dirs_at, deep, errors, max_file_depth, max_dir_depth, total_files)"""
    files_at = Counter()
    dirs_at = Counter()
    deep = []
    errors = []
    max_file_depth = 0
    max_dir_depth = 0
    total_files = 0

    def on_error(exc):
        errors.append(str(exc))

    for dirpath, _dirnames, filenames in os.walk(root, onerror=on_error):
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        dirs_at[depth] += 1
        if depth > max_dir_depth:
            max_dir_depth = depth
        if depth > threshold:
            deep.append((depth, os.path.join(dirpath, "")))
        for name in filenames:
            fdepth = depth + 1
            files_at[fdepth] += 1
            total_files += 1
            if fdepth > max_file_depth:
                max_file_depth = fdepth
            if fdepth > threshold:
                deep.append((fdepth, os.path.join(dirpath, name)))
    return files_at, dirs_at, deep, errors, max_file_depth, max_dir_depth, total_files


def main(argv=None):
    _safe_stdout()
    parser = argparse.ArgumentParser(
        description="统计目录树的最大深度与各深度层的文件分布，找出嵌套过深的路径。")
    parser.add_argument("directory", help="要统计的目录")
    parser.add_argument("-m", "--max-depth", type=int, default=8,
                        help="过深阈值（深度超过它即视为嵌套过深），默认 8")
    parser.add_argument("-l", "--limit", type=int, default=20,
                        help="过深路径最多显示条数，默认 20")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)

    root = args.directory
    if not os.path.isdir(root):
        print("错误: 目录不存在或不是目录: %s" % root, file=sys.stderr)
        return 2
    root = os.path.abspath(root)

    files_at, dirs_at, deep, errors, max_fd, max_dd, total_files = scan(
        root, args.max_depth)
    total_dirs = sum(dirs_at.values())
    deep.sort(key=lambda item: (-item[0], item[1]))
    show = max(0, args.limit)

    if args.json:
        payload = {
            "root": root,
            "max_file_depth": max_fd,
            "max_dir_depth": max_dd,
            "total_files": total_files,
            "total_dirs": total_dirs,
            "files_per_depth": {str(k): files_at[k] for k in sorted(files_at)},
            "dirs_per_depth": {str(k): dirs_at[k] for k in sorted(dirs_at)},
            "threshold": args.max_depth,
            "deep_total": len(deep),
            "deep": [{"depth": d, "path": p} for d, p in deep[:show]],
            "walk_errors": errors[:20],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("根目录: %s" % root)
    print("最大目录深度: %d    最大文件深度: %d" % (max_dd, max_fd))
    print("目录总数: %d    文件总数: %d" % (total_dirs, total_files))
    print()
    print("深度分布（第 0 层 = 根目录）:")
    print("%6s %8s %8s" % ("深度", "文件数", "目录数"))
    for depth in sorted(set(files_at) | set(dirs_at)):
        print("%6d %8d %8d" % (depth, files_at.get(depth, 0), dirs_at.get(depth, 0)))
    print()
    if deep:
        print("过深路径（深度 > %d）共 %d 条，最多显示 %d 条:"
              % (args.max_depth, len(deep), args.limit))
        for d, p in deep[:show]:
            print("  [%d] %s" % (d, p))
    else:
        print("过深路径（深度 > %d）: 无" % args.max_depth)
    print("无法访问的目录: %d 个" % len(errors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
