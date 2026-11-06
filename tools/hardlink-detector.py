#!/usr/bin/env python3
r"""硬链接检测器 (hardlink-detector)。

用途:
    递归扫描目录, 用 os.stat 的 st_ino / st_nlink (Windows 上 NTFS 同样提供)
    找出指向同一磁盘数据的多重硬链接文件组, 并统计这些硬链接已经节约的空间
    (即: 若它们是各自独立的完整副本, 还会额外占用的字节数)。
    只读分析, 不改动任何文件。

示例:
    python hardlink-detector.py "K:\data"
    python hardlink-detector.py "K:\data" "K:\more" --min-size 4096

退出码:
    0 = 正常; 2 = 参数或目录错误。
"""

import argparse
import os
import sys


def _setup_stdio():
    """Windows 下把输出流固定为 UTF-8, 避免中文输出在管道中触发编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def human_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{int(n)} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


def collect_files(roots):
    """递归收集所有普通文件的绝对路径, 跨根去重 (同一文件不会因重复传根而误判成硬链接)。"""
    seen = set()
    out = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for name in sorted(filenames):
                p = os.path.join(dirpath, name)
                try:
                    key = os.path.realpath(p)
                except OSError:
                    key = p
                if key in seen:
                    continue
                seen.add(key)
                out.append(p)
    return out


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(
        prog="hardlink-detector",
        description="通过 inode/st_nlink 找出同一文件的多重硬链接, 并统计已节约的重复空间。",
    )
    ap.add_argument("dirs", nargs="+", metavar="目录")
    ap.add_argument("--min-size", type=int, default=0, help="只统计大于该字节数的文件 (默认 0)")
    args = ap.parse_args(argv)

    roots = []
    for d in args.dirs:
        r = os.path.abspath(d)
        if not os.path.isdir(r):
            print(f"错误: 目录不存在: {r}", file=sys.stderr)
            return 2
        roots.append(r)

    files = collect_files(roots)
    print("== 硬链接检测报告 ==")
    print("扫描根: " + "  ".join(roots))
    print(f"扫描文件数: {len(files)}  (最小字节: {args.min_size})")

    stats = {}
    by_key = {}
    no_ino = 0
    for p in files:
        try:
            st = os.stat(p)
        except OSError:
            continue
        if st.st_size < args.min_size:
            continue
        stats[p] = st
        if not st.st_ino:
            no_ino += 1
            continue
        by_key.setdefault((st.st_dev, st.st_ino), []).append(p)

    counted = len(stats)
    if counted and no_ino == counted:
        print("警告: 文件系统未提供 inode 信息 (st_ino=0, 如 FAT32/exFAT), 无法检测硬链接。")
        return 0

    groups = []
    for key, ps in by_key.items():
        if len(ps) >= 2:
            ps = sorted(ps)
            size = stats[ps[0]].st_size
            nlink = stats[ps[0]].st_nlink
            groups.append((size, key, nlink, ps))
    groups.sort(key=lambda g: (-(g[0] * (len(g[3]) - 1)), g[3][0]))

    total_saved = sum(size * (len(ps) - 1) for size, _, _, ps in groups)
    total_files = sum(len(ps) for _, _, _, ps in groups)
    print(f"\n发现 {len(groups)} 组多重硬链接 (共 {total_files} 个文件), 已节约空间: {human_size(total_saved)}")

    for i, (size, (dev, ino), nlink, ps) in enumerate(groups, 1):
        print(f"\n组 {i}: 大小 {human_size(size)}  dev={dev}  inode={ino}  "
              f"st_nlink={nlink}  已节约 {human_size(size * (len(ps) - 1))}")
        for p in ps:
            print(f"  - {p}")
        if nlink > len(ps):
            print(f"  (!) 另有 {nlink - len(ps)} 个硬链接不在本次扫描范围内")

    partial = [(p, st) for p, st in stats.items()
               if st.st_ino and st.st_nlink > 1 and len(by_key.get((st.st_dev, st.st_ino), [])) < 2]
    if partial:
        saved_out = sum(st.st_size * (st.st_nlink - 1) for _, st in partial)
        print(f"\n另有 {len(partial)} 个文件 st_nlink>1 但在扫描范围内只找到 1 个路径"
              f" (其余链接在范围外), 对应已节约空间约 {human_size(saved_out)}。")

    if not groups and not partial:
        print("结果: 未发现多重硬链接 (所有文件都是独立数据)。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
