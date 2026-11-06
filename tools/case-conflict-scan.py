#!/usr/bin/env python3
"""大小写冲突扫描：找出目录中仅大小写不同的文件名对，预警跨平台（Windows/Linux）同步隐患。

用途
    扫描一个目录（默认不递归，可 --recursive）下的文件与子目录名，
    找出彼此仅大小写不同的名字对（如 ReadMe.txt 与 readme.txt）。
    这类文件在 Windows 上会被视为同一个文件，同步到 Linux 再同步回来
    时会互相覆盖，因此给出预警。退出码：发现冲突为 1，无冲突为 0。

示例命令
    python case-conflict-scan.py ./docs
    python case-conflict-scan.py . -r                  # 递归扫描
    python case-conflict-scan.py . -r --dirs           # 同时纳入目录名
    python case-conflict-scan.py ./repo -r --json      # 以 JSON 输出结果

参数
    directory    要扫描的目录
    -r/--recursive  递归扫描子目录
    --dirs       除文件外也扫描目录名
    --json       以 JSON 格式输出冲突清单
"""
import argparse
import json
import os
import sys
from collections import defaultdict

def scan(directory, recursive=False, include_dirs=False):
    """返回 {相对目录: [冲突对列表]}，冲突对为 (名字A, 名字B)。"""
    conflicts = {}
    if recursive:
        walker = os.walk(directory)
    else:
        # 非递归：实际列出目录内容，文件与子目录分列
        files, dirnames = [], []
        for e in os.listdir(directory):
            full = os.path.join(directory, e)
            if os.path.isdir(full):
                dirnames.append(e)
            else:
                files.append(e)
        walker = [(directory, dirnames, files)]
    for root, dirs, names in walker:
        if recursive:
            dirs.sort()
        entries = sorted(names)
        if include_dirs:
            entries += sorted(dirs)
        buckets = defaultdict(list)
        for name in entries:
            buckets[name.lower()].append(name)
        pairs = []
        for lower, names_in_bucket in sorted(buckets.items()):
            if len(names_in_bucket) > 1:
                pairs.append(tuple(names_in_bucket))
        if pairs:
            rel = os.path.relpath(root, directory)
            conflicts["." if rel == "." else rel] = pairs
    return conflicts

def main(argv=None):
    ap = argparse.ArgumentParser(description="扫描仅大小写不同的文件名对，预警跨平台同步隐患")
    ap.add_argument("directory", help="要扫描的目录")
    ap.add_argument("-r", "--recursive", action="store_true", help="递归扫描子目录")
    ap.add_argument("--dirs", action="store_true", help="同时把目录名纳入比对")
    ap.add_argument("--json", action="store_true", dest="as_json", help="以 JSON 输出")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.directory):
        print("错误：目录不存在：%s" % args.directory)
        return 2

    conflicts = scan(args.directory, args.recursive, args.dirs)

    if args.as_json:
        print(json.dumps(conflicts, ensure_ascii=False, indent=2))
    else:
        if not conflicts:
            print("未发现大小写冲突。")
        for rel, pairs in conflicts.items():
            for pair in pairs:
                print("冲突 [%s]: %s" % (rel, " <-> ".join(pair)))

    total = sum(len(v) for v in conflicts.values())
    if total:
        print("发现 %d 处大小写冲突，跨 Windows/Linux 同步时可能互相覆盖，建议重命名修正。" % total)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
