#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""duplicate-finder.py -- 三级过滤找出目录中的重复文件(内容相同)。

用途:
    按计算开销从低到高的三级策略逐层收窄候选, 避免对所有文件直接
    做全量哈希:
        第 1 级  大小过滤      文件大小不同 -> 内容必然不同;
        第 2 级  部分哈希过滤  对同大小文件读取首尾各 --partial-bytes
                               字节(默认 4096)计算摘要, 摘要不同 ->
                               内容必然不同;
        第 3 级  全量哈希确认  对幸存候选计算整个文件的摘要, 摘要
                               相同 -> 判定为重复。
    工具只读不写, 不删除、不修改任何文件; --json 便于管道处理。
    退出码: 0=正常完成(是否找到重复都不算错误), 2=用法/读取错误。

用法:
    python -I duplicate-finder.py <目录> [--algo sha256] [--partial-bytes 4096] [--json]

示例:
    $ python -I duplicate-finder.py ./downloads
    [group 1] sha256=e3b0c442...  size=0 bytes  copies=2
      downloads/a.zip
      downloads/b.zip
    scanned 120 files: 3 duplicate group(s), 4 extra copy(ies), 15.3 MiB wasted.
"""

import argparse
import hashlib
import json
import os
import sys

CHUNK = 1 << 20


def hash_partial(path, algo, head, tail):
    """Digest over the first `head` plus the last `tail` bytes (no overlap)."""
    h = hashlib.new(algo)
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        h.update(fh.read(head))
        if tail > 0 and size > head:
            fh.seek(max(size - tail, head))
            h.update(fh.read(tail))
    return h.hexdigest()


def hash_full(path, algo):
    h = hashlib.new(algo)
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def find_duplicates(root, algo, partial_bytes):
    """Return (scanned_file_count, groups); groups sorted by size then digest."""
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        for name in filenames:
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                continue
            try:
                size = os.path.getsize(path)
            except OSError as exc:
                print("WARN: cannot stat %s (%s)" % (path, exc), file=sys.stderr)
                continue
            files.append((path, size))

    by_size = {}
    for path, size in files:
        by_size.setdefault(size, []).append(path)

    groups = []
    for size in sorted(by_size):
        candidates = by_size[size]
        # -- level 1: size filter, unique size can never have a twin
        if len(candidates) < 2:
            continue
        # -- level 2: partial (head+tail) hash filter
        by_partial = {}
        for path in candidates:
            try:
                digest = hash_partial(path, algo, partial_bytes, partial_bytes)
            except OSError as exc:
                print("WARN: cannot read %s (%s)" % (path, exc), file=sys.stderr)
                continue
            by_partial.setdefault(digest, []).append(path)
        # -- level 3: full hash confirmation
        for paths in by_partial.values():
            if len(paths) < 2:
                continue
            by_full = {}
            for path in paths:
                try:
                    digest = hash_full(path, algo)
                except OSError as exc:
                    print("WARN: cannot read %s (%s)" % (path, exc), file=sys.stderr)
                    continue
                by_full.setdefault(digest, []).append(path)
            for digest, group in sorted(by_full.items()):
                if len(group) >= 2:
                    groups.append({"size": size, "hash": digest, "paths": sorted(group)})
    return len(files), groups


def human_size(n):
    size = float(n)
    for unit in ("bytes", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            if unit == "bytes":
                return "%d bytes" % int(size)
            return "%.1f %s" % (size, unit)
        size /= 1024.0


def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="duplicate-finder.py",
        description="Find duplicate files via size -> partial-hash -> full-hash filtering.")
    parser.add_argument("dir", help="directory to scan recursively")
    parser.add_argument("--algo", default="sha256",
                        help="hash algorithm (default: sha256)")
    parser.add_argument("--partial-bytes", type=int, default=4096, dest="partial_bytes",
                        help="head/tail bytes for the level-2 partial hash (default: 4096)")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON instead of text")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.dir):
        print("ERROR: not a directory: %s" % args.dir, file=sys.stderr)
        return 2
    if args.partial_bytes < 1:
        parser.error("--partial-bytes must be >= 1")
    try:
        hashlib.new(args.algo)
    except (ValueError, TypeError):
        parser.error("unknown hash algorithm: %s" % args.algo)

    scanned, groups = find_duplicates(args.dir, args.algo, args.partial_bytes)

    if args.json:
        payload = {
            "algo": args.algo,
            "partial_bytes": args.partial_bytes,
            "scanned_files": scanned,
            "duplicate_groups": groups,
        }
        print(json.dumps(payload, indent=2))
        return 0

    for i, group in enumerate(groups, 1):
        print("[group %d] %s=%s  size=%d bytes  copies=%d"
              % (i, args.algo, group["hash"], group["size"], len(group["paths"])))
        for path in group["paths"]:
            print("  %s" % path)
    extra = sum(len(g["paths"]) - 1 for g in groups)
    wasted = sum(g["size"] * (len(g["paths"]) - 1) for g in groups)
    print("scanned %d files: %d duplicate group(s), %d extra copy(ies), %s wasted."
          % (scanned, len(groups), extra, human_size(wasted)))
    return 0


if __name__ == "__main__":
    _utf8_stdio()
    sys.exit(main())
