#!/usr/bin/env python3
"""重复文件查找工具：先按文件大小、再按内容哈希（SHA-256）两级比对找出重复文件。

支持三种动作：
  report      仅打印重复报告（默认动作，不做任何修改）
  quarantine  把每组重复的副本移入隔离目录（每组按路径排序，保留第一个为正本）
  delete      直接删除每组重复的副本

用法示例：
  python dedupe-by-hash.py report data_dir
  python dedupe-by-hash.py quarantine --quarantine-dir ./quarantine data_dir
  python dedupe-by-hash.py delete data_dir

退出码：0 表示正常完成（无论是否发现重复）。
"""
import argparse
import hashlib
import os
import shutil
import sys
from collections import defaultdict

CHUNK = 1 << 20


def iter_files(paths):
    """展开输入：文件直接产出，目录递归产出其中所有文件。"""
    for p in paths:
        if os.path.isfile(p):
            yield p
        elif os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for name in sorted(files):
                    yield os.path.join(root, name)
        else:
            print("警告：路径不存在，跳过：%s" % p, file=sys.stderr)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def unique_path(directory, name):
    """在 directory 中为 name 找一个不冲突的名字：name(1).ext、name(2).ext ..."""
    base, ext = os.path.splitext(name)
    cand = os.path.join(directory, name)
    n = 1
    while os.path.exists(cand):
        cand = os.path.join(directory, "%s(%d)%s" % (base, n, ext))
        n += 1
    return cand


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="按 大小 -> 内容哈希 两级比对查找重复文件")
    ap.add_argument("action", nargs="?", choices=["report", "quarantine", "delete"],
                    default="report", help="动作：report / quarantine / delete（默认 report）")
    ap.add_argument("paths", nargs="+", metavar="PATH", help="要扫描的文件或目录")
    ap.add_argument("--quarantine-dir", default="./quarantine",
                    help="隔离目录（quarantine 动作使用，默认 ./quarantine）")
    # parse_intermixed_args 允许选项（如 --quarantine-dir）出现在位置参数之间
    args = ap.parse_intermixed_args(argv)

    # 第一级：按文件大小分组
    by_size = defaultdict(list)
    for fp in iter_files(args.paths):
        try:
            by_size[os.path.getsize(fp)].append(fp)
        except OSError as e:
            print("跳过无法访问的文件：%s（%s）" % (fp, e), file=sys.stderr)

    # 第二级：大小相同的组内再按内容哈希分组
    dup_groups = []
    for size, files in by_size.items():
        if len(files) < 2:
            continue
        by_hash = defaultdict(list)
        for fp in files:
            try:
                by_hash[sha256_file(fp)].append(fp)
            except OSError as e:
                print("跳过无法读取的文件：%s（%s）" % (fp, e), file=sys.stderr)
        for group in by_hash.values():
            if len(group) > 1:
                dup_groups.append(sorted(group))
    dup_groups.sort(key=lambda g: g[0])

    if not dup_groups:
        print("未发现重复文件。")
        return 0

    total_copies = sum(len(g) - 1 for g in dup_groups)
    wasted = sum(os.path.getsize(g[0]) * (len(g) - 1) for g in dup_groups)
    print("发现 %d 组重复文件，共 %d 个副本，占用 %.1f KB："
          % (len(dup_groups), total_copies, wasted / 1024.0))

    moved = deleted = errors = 0
    if args.action == "quarantine":
        os.makedirs(args.quarantine_dir, exist_ok=True)

    for i, group in enumerate(dup_groups, 1):
        original, copies = group[0], group[1:]
        print("\n[组 %d] 正本：%s" % (i, original))
        for cp in copies:
            print("  副本：%s" % cp)
            if args.action == "quarantine":
                try:
                    dest = unique_path(args.quarantine_dir, os.path.basename(cp))
                    shutil.move(cp, dest)
                    print("    -> 已移入隔离：%s" % dest)
                    moved += 1
                except OSError as e:
                    print("    -> 移动失败：%s" % e, file=sys.stderr)
                    errors += 1
            elif args.action == "delete":
                try:
                    os.remove(cp)
                    print("    -> 已删除")
                    deleted += 1
                except OSError as e:
                    print("    -> 删除失败：%s" % e, file=sys.stderr)
                    errors += 1

    if args.action == "quarantine":
        print("\n完成：移入隔离 %d 个，失败 %d 个。" % (moved, errors))
    elif args.action == "delete":
        print("\n完成：删除 %d 个，失败 %d 个。" % (deleted, errors))
    else:
        print("\n（report 模式，未做任何修改；用 quarantine 或 delete 处理副本）")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
