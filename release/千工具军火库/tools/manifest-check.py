#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""manifest-check.py -- 用 manifest.json 清单核验目录完整性。

用途:
    create 子命令扫描目录, 为每个文件记录 相对路径/字节大小/摘要,
    写入 manifest.json; check 子命令重新扫描并对照清单, 列出:
        ADDED     目录中新增、清单里没有的文件
        REMOVED   清单里有、目录中已被删除的文件
        MODIFIED  文件仍在但摘要(或大小)与清单不符, 即被篡改/改动
    摘要算法可选 md5/sha1/sha256/sha512/blake2b, 默认 sha256。
    清单文件本身自动排除在扫描之外, 不会把自己标成 ADDED。
    退出码: 0=全部一致, 1=发现差异, 2=用法或读取错误。

用法:
    python -I manifest-check.py create <目录> [-m manifest.json] [--algo sha256] [--force]
    python -I manifest-check.py check  <目录> [-m manifest.json]

示例:
    $ python -I manifest-check.py create ./dist -m dist.manifest.json
    created manifest: dist.manifest.json (12 files, sha256)
    $ python -I manifest-check.py check ./dist -m dist.manifest.json
    OK: 12 files verified, no changes.
"""

import argparse
import hashlib
import json
import os
import sys

CHUNK = 1 << 20
SUPPORTED_ALGOS = ("md5", "sha1", "sha256", "sha512", "blake2b")


def hash_file(path, algo):
    """Return (hexdigest, size) of a file, streamed in chunks."""
    h = hashlib.new(algo)
    size = 0
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def iter_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                continue
            yield path


def rel_key(path, root):
    return os.path.relpath(path, root).replace(os.sep, "/")


def scan_tree(root, algo, exclude_abs):
    """Map relative-key -> {size, digest} for every readable file under root."""
    files = {}
    for path in iter_files(root):
        if os.path.abspath(path) in exclude_abs:
            continue
        try:
            digest, size = hash_file(path, algo)
        except OSError as exc:
            print("WARN: cannot read %s (%s)" % (path, exc), file=sys.stderr)
            continue
        files[rel_key(path, root)] = {"size": size, algo: digest}
    return files


def cmd_create(args):
    if not os.path.isdir(args.dir):
        print("ERROR: not a directory: %s" % args.dir, file=sys.stderr)
        return 2
    if os.path.exists(args.manifest) and not args.force:
        print("ERROR: manifest already exists: %s (use --force to overwrite)"
              % args.manifest, file=sys.stderr)
        return 2
    exclude = {os.path.abspath(args.manifest)}
    files = scan_tree(args.dir, args.algo, exclude)
    manifest = {
        "manifest-version": 1,
        "algorithm": args.algo,
        "root": os.path.abspath(args.dir),
        "files": files,
    }
    with open(args.manifest, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("created manifest: %s (%d files, %s)" % (args.manifest, len(files), args.algo))
    return 0


def cmd_check(args):
    try:
        with open(args.manifest, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        print("ERROR: cannot load manifest %s: %s" % (args.manifest, exc), file=sys.stderr)
        return 2
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        print("ERROR: %s is not a manifest-check manifest" % args.manifest, file=sys.stderr)
        return 2
    algo = manifest.get("algorithm", "sha256")
    if algo not in SUPPORTED_ALGOS:
        print("ERROR: unsupported algorithm in manifest: %s" % algo, file=sys.stderr)
        return 2
    if not os.path.isdir(args.dir):
        print("ERROR: not a directory: %s" % args.dir, file=sys.stderr)
        return 2

    exclude = {os.path.abspath(args.manifest)}
    current = scan_tree(args.dir, algo, exclude)
    expected = manifest["files"]

    added = sorted(k for k in current if k not in expected)
    removed = sorted(k for k in expected if k not in current)
    modified = []
    for key in sorted(set(expected) & set(current)):
        old = expected[key]
        now = current[key]
        if old.get(algo) != now[algo] or old.get("size") != now["size"]:
            modified.append((key, old.get(algo, "?"), now[algo]))

    if not added and not removed and not modified:
        print("OK: %d files verified, no changes." % len(current))
        return 0

    print("DIFF: %d added, %d removed, %d modified"
          % (len(added), len(removed), len(modified)))
    for key in added:
        print("  ADDED    %s" % key)
    for key in removed:
        print("  REMOVED  %s" % key)
    for key, old_digest, new_digest in modified:
        print("  MODIFIED %s" % key)
        print("           manifest %s" % _short(old_digest))
        print("           actual   %s" % _short(new_digest))
    return 1


def _short(digest):
    if isinstance(digest, str) and len(digest) > 16:
        return digest[:16] + "..."
    return digest


def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="manifest-check.py",
        description="Verify a directory against a manifest.json (list added/removed/modified files).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="scan a directory and write a manifest")
    p_create.add_argument("dir")
    p_create.add_argument("-m", "--manifest", default="manifest.json",
                          help="manifest path to write (default: ./manifest.json)")
    p_create.add_argument("--algo", default="sha256", choices=SUPPORTED_ALGOS,
                          help="hash algorithm (default: sha256)")
    p_create.add_argument("--force", action="store_true",
                          help="overwrite an existing manifest")
    p_create.set_defaults(func=cmd_create)

    p_check = sub.add_parser("check", help="verify a directory against a manifest")
    p_check.add_argument("dir")
    p_check.add_argument("-m", "--manifest", default="manifest.json",
                         help="manifest path to verify against (default: ./manifest.json)")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    _utf8_stdio()
    sys.exit(main())
