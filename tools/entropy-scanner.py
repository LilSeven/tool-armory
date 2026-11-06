#!/usr/bin/env python3
"""entropy-scanner.py —— 文件熵扫描器

用途:
    计算文件(或其抽样)的字节级香农熵(0~8 bit/byte), 结合压缩容器魔数把文件
    粗分为四类并汇总统计:

        <= 5.5    uncompressed   文本/源码等未压缩数据(英文文本约 4.1~4.8)
        5.5 ~ 7.2 medium         中等熵(混合内容、部分压缩、数据库页等)
        7.2 ~ 7.9 compressed     无容器魔数的高熵数据(典型裸压缩流)
        > 7.9     encrypted?     接近满熵且无压缩容器魔数, 可能加密或强随机

    另: 文件头命中已知压缩容器魔数(zip/gzip/bzip2/xz/7z/rar/zstd/cab)时直接
    判为 compressed —— 压缩流熵普遍高达 7.9+, 单凭熵值无法与加密数据区分,
    必须借助文件头。最终结论仍建议用 hex-head-dump 人工复核。

示例命令:
    python entropy-scanner.py file1.bin file2.gz        # 扫描指定文件
    python entropy-scanner.py ./data -r                 # 递归扫描目录
    python entropy-scanner.py ./data -r -v              # 列出全部文件的明细
    python entropy-scanner.py big.img --max-bytes 262144  # 大文件只抽样 256KB

说明:
    - 默认每个文件最多读取 1 MiB; 超过上限的文件会在文件内均匀抽样 16 段。
    - 空文件记为 empty, 不参与平均熵统计。
    - 退出码: 0=正常完成; 1=存在读取错误(如路径不存在)。
仅用 Python 标准库。
"""

import argparse
import fnmatch
import math
import os
import sys

LOW_MAX = 5.5       # <= : uncompressed
HIGH_MIN = 7.2      # >= : compressed
VHIGH_MIN = 7.9     # >  : encrypted?
SAMPLE_CHUNKS = 16
CLASS_ORDER = ("empty", "uncompressed", "medium", "compressed", "encrypted?")

COMPRESSED_MAGICS = (
    b"PK\x03\x04", b"PK\x05\x06",   # zip / empty zip
    b"\x1f\x8b",                    # gzip
    b"BZh",                         # bzip2
    b"\xfd7zXZ\x00",                # xz
    b"7z\xbc\xaf\x27\x1c",          # 7z
    b"Rar!\x1a\x07",                # rar
    b"\x28\xb5\x2f\xfd",            # zstd
    b"MSCF",                        # MS cab
)


def has_compressed_magic(data):
    return any(data.startswith(m) for m in COMPRESSED_MAGICS)


def shannon_entropy(data):
    """Shannon entropy of byte values, in bits/byte (0.0 ~ 8.0)."""
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    total = len(data)
    h = 0.0
    for c in counts:
        if c:
            p = c / total
            h -= p * math.log2(p)
    return h


def sample(path, size, max_bytes):
    """Read up to max_bytes: whole file, or SAMPLE_CHUNKS evenly spaced chunks."""
    if size <= max_bytes:
        with open(path, "rb") as fh:
            return fh.read()
    per = max(1, max_bytes // SAMPLE_CHUNKS)
    last = size - per
    out = bytearray()
    with open(path, "rb") as fh:
        for i in range(SAMPLE_CHUNKS):
            off = last * i // (SAMPLE_CHUNKS - 1) if SAMPLE_CHUNKS > 1 else 0
            fh.seek(off)
            out += fh.read(per)
    return bytes(out)


def classify(h, size, data=b""):
    if size == 0:
        return "empty"
    if has_compressed_magic(data):
        return "compressed"
    if h <= LOW_MAX:
        return "uncompressed"
    if h < HIGH_MIN:
        return "medium"
    if h <= VHIGH_MIN:
        return "compressed"
    return "encrypted?"


def discover(paths, recursive, includes, excludes):
    """Expand input paths into a flat, deterministic file list.

    Returns (files, missing).
    """
    files, missing = [], []
    seen = set()

    def wanted(path):
        name = os.path.basename(path)
        if excludes and any(fnmatch.fnmatch(name, pat) for pat in excludes):
            return False
        if includes and not any(fnmatch.fnmatch(name, pat) for pat in includes):
            return False
        return True

    for p in paths:
        key = os.path.abspath(p)
        if key in seen:
            continue
        seen.add(key)
        if os.path.isfile(p):
            if wanted(p):
                files.append(p)
        elif os.path.isdir(p):
            if recursive:
                for root, dirs, names in os.walk(p):
                    dirs[:] = sorted(
                        d for d in dirs
                        if not (excludes and any(fnmatch.fnmatch(d, pat) for pat in excludes))
                    )
                    for n in sorted(names):
                        fp = os.path.join(root, n)
                        if wanted(fp):
                            files.append(fp)
            else:
                for n in sorted(os.listdir(p)):
                    fp = os.path.join(p, n)
                    if os.path.isfile(fp) and wanted(fp):
                        files.append(fp)
        else:
            missing.append(p)
    return files, missing


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="entropy-scanner.py",
        description="Scan files' byte entropy and classify them as uncompressed / "
                    "medium / compressed / encrypted?, with summary statistics.")
    parser.add_argument("paths", nargs="+", metavar="PATH",
                        help="file or directory (use -r to recurse)")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="recurse into directories")
    parser.add_argument("--max-bytes", type=int, default=1 << 20, metavar="N",
                        help="max bytes sampled per file (default: 1048576)")
    parser.add_argument("--include", action="append", default=[], metavar="GLOB",
                        help="only process files whose name matches GLOB (repeatable)")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="skip files/dirs whose name matches GLOB (repeatable)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="list every file (default: only compressed / encrypted?)")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass

    if args.max_bytes <= 0:
        parser.error("--max-bytes must be a positive integer")

    files, missing = discover(args.paths, args.recursive, args.include, args.exclude)
    errors = 0
    for p in missing:
        print("error: path not found: %s" % p, file=sys.stderr)
        errors += 1

    rows = []
    class_counts = dict.fromkeys(CLASS_ORDER, 0)
    ent_list = []
    total_sampled = 0

    for path in files:
        try:
            size = os.path.getsize(path)
            data = sample(path, size, args.max_bytes)
        except OSError as exc:
            print("error: cannot read %s: %s" % (path, exc), file=sys.stderr)
            errors += 1
            continue
        h = shannon_entropy(data)
        cls = classify(h, size, data)
        class_counts[cls] += 1
        total_sampled += len(data)
        if size > 0:
            ent_list.append(h)
        rows.append((h, cls, size, path))

    interesting = [r for r in rows if r[1] in ("compressed", "encrypted?")]
    for h, cls, size, path in (rows if args.verbose else interesting):
        print("%.4f  %-12s %10d B  %s" % (h, cls, size, path))

    print("-" * 64)
    print("scanned: %d file(s), sampled %d bytes, errors: %d"
          % (len(rows), total_sampled, errors))
    present = [(k, class_counts[k]) for k in CLASS_ORDER if class_counts[k]]
    print("classes: " + ("  ".join("%s=%d" % kv for kv in present) or "(none)"))
    if ent_list:
        print("entropy: avg=%.4f min=%.4f max=%.4f (over %d non-empty file(s))"
              % (sum(ent_list) / len(ent_list), min(ent_list), max(ent_list),
                 len(ent_list)))
    if interesting:
        print("high-entropy files (compressed / encrypted?): %d" % len(interesting))
        for h, cls, size, path in interesting:
            print("  - %s (%.4f bits/byte, %s)" % (path, h, cls))
    else:
        print("high-entropy files (compressed / encrypted?): none")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
