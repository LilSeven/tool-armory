"""空目录清理 —— 递归删除目录树中的空目录（包括子目录清理后变空的父目录）。

用法:
    python empty-dir-cleaner.py <目录> [--dry-run] [--keep-root]

示例:
    python empty-dir-cleaner.py D:/tmp/tree --dry-run      # 仅列出待删的空目录清单
    python empty-dir-cleaner.py D:/tmp/tree                # 实际删除
    python empty-dir-cleaner.py D:/tmp/tree --keep-root    # 删除子空目录但保留根目录本身

说明:
    自底向上遍历（os.walk(topdown=False)），子目录清空后父目录也会被删除。
    --dry-run 只打印待删清单，不做任何修改。退出码 0 表示成功。
"""

import argparse
import os
import sys


def collect_empty_dirs(root: str, keep_root: bool):
    """自底向上收集空目录，返回按删除顺序（深->浅）排列的列表。

    判定规则：某目录为空，当且仅当它没有文件，且其所有子目录都已被判定为空。
    """
    empty = []
    empty_set = set()
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        remaining = [d for d in dirnames if os.path.join(dirpath, d) not in empty_set]
        if remaining or filenames:
            continue
        if keep_root and os.path.abspath(dirpath) == os.path.abspath(root):
            continue
        empty.append(dirpath)
        empty_set.add(dirpath)
    return empty


def main(argv=None):
    p = argparse.ArgumentParser(description="递归删除空目录（含清空后的父目录）")
    p.add_argument("root", help="要清理的根目录")
    p.add_argument("--dry-run", action="store_true", help="仅列出待删清单，不删除")
    p.add_argument("--keep-root", action="store_true", help="保留根目录本身（即使它变空）")
    args = p.parse_args(argv)

    root = args.root
    if not os.path.isdir(root):
        print(f"错误: 不是目录: {root}", file=sys.stderr)
        return 2

    empty_dirs = collect_empty_dirs(root, args.keep_root)
    if not empty_dirs:
        print("没有发现空目录。")
        return 0

    mode = "[dry-run] " if args.dry_run else ""
    for d in empty_dirs:
        print(f"{mode}删除: {d}")
    if not args.dry_run:
        failed = 0
        for d in empty_dirs:
            try:
                os.rmdir(d)
            except OSError as e:
                print(f"警告: 删除失败 {d}: {e}", file=sys.stderr)
                failed += 1
        print(f"共删除 {len(empty_dirs) - failed} 个空目录。")
    else:
        print(f"共 {len(empty_dirs)} 个空目录待删（未执行）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
