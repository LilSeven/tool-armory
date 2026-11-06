#!/usr/bin/env python3
"""目录镜像同步：使目标目录与源目录完全一致（复制新增与变更、删除多余文件），默认预演。

用法:
  python mirror-dirs.py <源目录> <目标目录> [--execute] [--by-hash] [--exclude "pattern1,pattern2"]

选项:
  --execute  实际执行同步；缺省为预演模式，仅打印将要做的操作
  --by-hash  用内容哈希(SHA-256)判断文件是否变更（默认用 大小+纳秒级 mtime，
             元数据完全相同无法区分时自动回退哈希，确保不漏检）
  --exclude  逗号分隔的 fnmatch 通配符，匹配到的文件/目录不参与同步

行为:
  - 源有目标没有：复制
  - 两边都有但内容不同：覆盖复制
  - 目标有源没有：删除
  - 源中为空目录：目标中创建（目录本身始终镜像）

示例命令:
  python mirror-dirs.py D:/src E:/backup                 # 预演
  python mirror-dirs.py D:/src E:/backup --execute      # 真正同步
  python mirror-dirs.py D:/src E:/backup --execute --exclude "*.tmp,.git"
"""

import argparse
import fnmatch
import hashlib
import os
import shutil
import sys


def excluded(rel: str, patterns) -> bool:
    rel = rel.replace(os.sep, "/")
    for p in patterns:
        p = p.strip().replace("\\", "/")
        if not p:
            continue
        if fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(os.path.basename(rel), p):
            return True
        # 目录前缀匹配: pattern "build" 应排除 build/xxx
        if not p.endswith("*") and "/" not in p and f"{p}/" in rel + "/":
            return True
    return False


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def changed(src: str, dst: str, by_hash: bool) -> bool:
    if os.path.getsize(src) != os.path.getsize(dst):
        return True
    if by_hash:
        return file_sha256(src) != file_sha256(dst)
    m1 = os.stat(src).st_mtime_ns
    m2 = os.stat(dst).st_mtime_ns
    if m1 != m2:
        return True
    # 大小与纳秒级 mtime 完全相同、元数据无法区分时，回退哈希判定，
    # 避免同秒写入/被显式设置了相同时间戳而内容不同的文件漏检
    return file_sha256(src) != file_sha256(dst)


def walk_files(root: str, patterns):
    """返回 {相对路径: 绝对路径}，跳过被排除项"""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir != ".":
            if excluded(rel_dir, patterns):
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames
                           if not excluded(os.path.join(rel_dir, d), patterns)]
        for fn in filenames:
            rel = fn if rel_dir == "." else os.path.join(rel_dir, fn)
            if excluded(rel, patterns):
                continue
            out[rel] = os.path.join(dirpath, fn)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="镜像同步目录，默认预演")
    ap.add_argument("src", help="源目录")
    ap.add_argument("dst", help="目标目录")
    ap.add_argument("--execute", action="store_true", help="实际执行（默认预演）")
    ap.add_argument("--by-hash", action="store_true", help="用 SHA-256 判断变更")
    ap.add_argument("--exclude", default="", help='排除通配符, 逗号分隔, 如 "*.tmp,.git"')
    args = ap.parse_args(argv)

    src = os.path.abspath(args.src)
    dst = os.path.abspath(args.dst)
    if not os.path.isdir(src):
        print(f"错误: 源目录不存在: {src}", file=sys.stderr)
        return 2
    if src == dst or dst in (src + os.sep, src + "/"):
        print("错误: 目标不能等于源（或源位于目标内部）", file=sys.stderr)
        return 2

    patterns = [p for p in args.exclude.split(",") if p.strip()]
    src_files = walk_files(src, patterns)
    dst_files = walk_files(dst, patterns)

    to_copy = [r for r in sorted(src_files)
               if r not in dst_files or changed(src_files[r], dst_files[r], args.by_hash)]
    to_delete = [r for r in sorted(dst_files) if r not in src_files]

    tag = "" if args.execute else "[预演] "
    n_copy = n_del = 0
    for rel in to_copy:
        target = os.path.join(dst, rel)
        print(f"{tag}复制 {src_files[rel]} -> {target}")
        if args.execute:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(src_files[rel], target)
        n_copy += 1
    for rel in to_delete:
        target = os.path.join(dst, rel)
        print(f"{tag}删除 {target}")
        if args.execute:
            os.remove(target)
        n_del += 1

    # 镜像空目录（只创建，不删除目标多余目录，避免误删）
    for dirpath, dirnames, _ in os.walk(src):
        for d in list(dirnames):
            rel = os.path.relpath(os.path.join(dirpath, d), src)
            if excluded(rel, patterns):
                continue
            target = os.path.join(dst, rel)
            if not os.path.isdir(target):
                print(f"{tag}建目录 {target}")
                if args.execute:
                    os.makedirs(target, exist_ok=True)

    verb = "已同步" if args.execute else "预演完成（加 --execute 执行）"
    print(f"{verb}: 复制/更新 {n_copy} 个，删除 {n_del} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
