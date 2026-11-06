#!/usr/bin/env python3
r"""跨目录重复对比 (dup-across-dirs)。

用途:
    对比目录 A 与目录 B 中的文件内容 (按字节哈希):
      * 列出 A 中与 B 中某文件内容完全相同的文件 (重复项 —— B 里已有同样内容);
      * 列出 A 中独有的文件 (B 中不存在相同内容)。
    只读分析, 不改动任何文件。

示例:
    python dup-across-dirs.py "K:\new" "K:\backup"
    python dup-across-dirs.py "K:\new" "K:\backup" --min-size 1

退出码:
    0 = 正常; 2 = 参数或目录错误。
"""

import argparse
import hashlib
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


def collect_files(root):
    """递归收集目录下所有普通文件的绝对路径, 排序保证结果稳定。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            out.append(os.path.join(dirpath, name))
    return out


def hash_file(path, alg="sha256", chunk=1 << 20):
    h = hashlib.new(alg)
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def index_dir(root, min_size, alg):
    """对目录建立 内容哈希 -> [路径] 索引, 返回 (索引, 参与文件数)。"""
    index = {}
    n = 0
    for p in collect_files(root):
        try:
            st = os.stat(p)
        except OSError:
            continue
        if st.st_size < min_size:
            continue
        try:
            digest = hash_file(p, alg)
        except OSError:
            continue
        index.setdefault(digest, []).append(p)
        n += 1
    return index, n


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(
        prog="dup-across-dirs",
        description="对比目录 A 与 B: 列出 A 中与 B 内容重复的文件以及 A 独有的文件。",
    )
    ap.add_argument("dir_a", metavar="目录A")
    ap.add_argument("dir_b", metavar="目录B")
    ap.add_argument("--min-size", type=int, default=0, help="只比较大于该字节数的文件 (默认 0)")
    ap.add_argument("--hash-alg", default="sha256", help="哈希算法 (默认 sha256)")
    args = ap.parse_args(argv)

    try:
        hashlib.new(args.hash_alg)
    except Exception:
        ap.error(f"未知哈希算法: {args.hash_alg}")

    a = os.path.abspath(args.dir_a)
    b = os.path.abspath(args.dir_b)
    for r in (a, b):
        if not os.path.isdir(r):
            print(f"错误: 目录不存在: {r}", file=sys.stderr)
            return 2

    index_b, n_b = index_dir(b, args.min_size, args.hash_alg)
    dups, uniq = [], []
    a_scanned = 0
    for p in collect_files(a):
        try:
            st = os.stat(p)
        except OSError:
            continue
        if st.st_size < args.min_size:
            continue
        a_scanned += 1
        try:
            digest = hash_file(p, args.hash_alg)
        except OSError:
            continue
        hits = index_b.get(digest)
        if hits:
            dups.append((p, st.st_size, hits))
        else:
            uniq.append((p, st.st_size))
    dups.sort()
    uniq.sort()
    dup_bytes = sum(s for _, s, _ in dups)
    uniq_bytes = sum(s for _, s in uniq)

    print("== 跨目录重复对比 ==")
    print(f"A: {a}")
    print(f"B: {b}")
    print(f"扫描: A 中参与比较 {a_scanned} 个文件; B 中已索引 {n_b} 个文件 (算法 {args.hash_alg})")

    print(f"\n-- A 中与 B 内容重复 ({len(dups)} 个, 合计 {human_size(dup_bytes)}) --")
    if dups:
        for p, size, hits in dups:
            extra = f"  (B 中另有 {len(hits) - 1} 个同内容文件)" if len(hits) > 1 else ""
            print(f"[重复] {p}  ({human_size(size)})  <->  {hits[0]}{extra}")
    else:
        print("(无)")

    print(f"\n-- A 独有 ({len(uniq)} 个, 合计 {human_size(uniq_bytes)}) --")
    if uniq:
        for p, size in uniq:
            print(f"[独有] {p}  ({human_size(size)})")
    else:
        print("(无)")

    print(f"\n小结: A 中 {len(dups)} 个文件的内容 B 里已有 (合计 {human_size(dup_bytes)}, 可考虑清理); "
          f"A 独有 {len(uniq)} 个 ({human_size(uniq_bytes)})。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
