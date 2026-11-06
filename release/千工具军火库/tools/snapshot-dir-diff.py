#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""snapshot-dir-diff.py —— 目录快照对比工具（仅用 Python 标准库）。

先给目录拍一份“哈希快照”存档为 JSON；之后把任意目录与快照对比，
找出被 新增 / 删除 / 修改（大小或哈希变化）的文件。
适合在改动前后各拍一次、或配合定时任务检测目录是否被意外变更。

示例命令:
    python snapshot-dir-diff.py snapshot ./webroot -o webroot.snap.json
    python snapshot-dir-diff.py diff webroot.snap.json              # 与快照原目录比
    python snapshot-dir-diff.py diff webroot.snap.json ./backup     # 与另一目录比

子命令:
    snapshot SRC_DIR -o SNAP.json [--algo sha256] [--exclude PAT ...]
        生成快照文件（记录每个文件的相对路径、大小、哈希）。
    diff SNAP.json [CUR_DIR] [--max-report N]
        对比快照与目录；发现差异时退出码为 1。

退出码:
    snapshot 子命令:  0 = 成功,  2 = 错误
    diff 子命令:      0 = 与快照一致,  1 = 发现差异,  2 = 错误
"""

import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import sys

CHUNK_SIZE = 1 << 16
SNAPSHOT_VERSION = 1


def setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def hash_file(path, algo):
    try:
        digest = hashlib.new(algo)
    except ValueError:
        return None
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(CHUNK_SIZE), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def scan_tree(root, algo, excludes):
    """遍历目录，返回 {相对路径: {"size": int, "hash": str|None}}。"""
    files = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            if not os.path.isfile(full):
                continue
            rel = os.path.relpath(full, root).replace("\\", "/")
            if any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat)
                   for pat in excludes):
                continue
            try:
                size = os.path.getsize(full)
            except OSError:
                size = -1
            files[rel] = {"size": size, "hash": hash_file(full, algo)}
    return files


def brief(entry):
    digest = entry.get("hash")
    hash_text = digest[:12] if digest else "(无)"
    return f"size={entry.get('size')}, hash={hash_text}"


def cmd_snapshot(args):
    if not os.path.isdir(args.src):
        print(f"错误: 目录不存在或不是目录: {args.src}", file=sys.stderr)
        return 2
    try:
        hashlib.new(args.algo)
    except ValueError:
        print(f"错误: 未知哈希算法: {args.algo}", file=sys.stderr)
        return 2

    files = scan_tree(args.src, args.algo, args.exclude)
    snapshot = {
        "tool": "snapshot-dir-diff",
        "version": SNAPSHOT_VERSION,
        "algo": args.algo,
        "root": os.path.abspath(args.src),
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "file_count": len(files),
        "files": files,
    }
    try:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, ensure_ascii=False, indent=2,
                      sort_keys=True)
    except OSError as exc:
        print(f"错误: 无法写入快照文件: {exc}", file=sys.stderr)
        return 2
    print(f"快照已保存: {args.out}")
    print(f"  目录: {snapshot['root']}  文件数: {len(files)}  算法: {args.algo}")
    return 0


def cmd_diff(args):
    try:
        with open(args.snap, "r", encoding="utf-8-sig") as fh:
            snapshot = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"错误: 无法读取快照文件: {exc}", file=sys.stderr)
        return 2
    snap_files = snapshot.get("files")
    if not isinstance(snap_files, dict):
        print("错误: 快照文件缺少 files 字段或格式不符", file=sys.stderr)
        return 2
    bad_entries = [rel for rel, entry in snap_files.items()
                   if not isinstance(entry, dict)]
    if bad_entries:
        print(f"错误: 快照文件中 {len(bad_entries)} 个条目格式不符，"
              f"如 {bad_entries[0]}", file=sys.stderr)
        return 2

    root = args.dir or snapshot.get("root")
    if not root or not os.path.isdir(root):
        print(f"错误: 待检查目录不存在: {root}", file=sys.stderr)
        return 2
    algo = snapshot.get("algo", "sha256")
    try:
        hashlib.new(algo)
    except ValueError:
        print(f"错误: 快照中的哈希算法不可用: {algo}", file=sys.stderr)
        return 2

    current = scan_tree(root, algo, [])
    added = sorted(set(current) - set(snap_files))
    removed = sorted(set(snap_files) - set(current))
    changed = sorted(
        rel for rel in set(current) & set(snap_files)
        if current[rel]["size"] != snap_files[rel].get("size")
        or current[rel]["hash"] != snap_files[rel].get("hash"))

    groups = [
        ("修改", [f"~ [修改] {rel}  快照[{brief(snap_files[rel])}] -> "
                  f"当前[{brief(current[rel])}]" for rel in changed]),
        ("新增", [f"+ [新增] {rel}  (当前 {brief(current[rel])})"
                  for rel in added]),
        ("删除", [f"- [删除] {rel}  (快照 {brief(snap_files[rel])})"
                  for rel in removed]),
    ]
    for label, lines in groups:
        cap = len(lines) if args.max_report == 0 else args.max_report
        for line in lines[:cap]:
            print(line)
        if len(lines) > cap:
            print(f"  ...（{label}类还有 {len(lines) - cap} 条未显示）")

    if added or removed or changed:
        print(f"摘要: 相对快照 新增 {len(added)}, 删除 {len(removed)}, "
              f"修改 {len(changed)}"
              f"（目录: {os.path.abspath(root)}, 算法 {algo}）。")
        return 1
    print(f"目录与快照一致（{len(current)} 个文件，算法 {algo}）。")
    return 0


def main(argv=None):
    setup_stdio()
    parser = argparse.ArgumentParser(
        prog="snapshot-dir-diff",
        description="给目录拍哈希快照存档，之后对比快照找出被变更的文件。")
    sub = parser.add_subparsers(dest="command", required=True)

    p_snap = sub.add_parser("snapshot", help="给目录拍哈希快照并存档为 JSON")
    p_snap.add_argument("src", help="要快照的目录")
    p_snap.add_argument("-o", "--out", required=True, help="快照输出文件（JSON）")
    p_snap.add_argument("--algo", default="sha256", help="哈希算法（默认 sha256）")
    p_snap.add_argument("--exclude", action="append", default=[],
                        help="排除规则（fnmatch 通配，可多次给出）")
    p_snap.set_defaults(func=cmd_snapshot)

    p_diff = sub.add_parser("diff", help="把目录与已有快照对比")
    p_diff.add_argument("snap", help="快照文件（JSON）")
    p_diff.add_argument("dir", nargs="?", default=None,
                        help="待检查目录（缺省用快照里记录的原目录）")
    p_diff.add_argument("--max-report", type=int, default=100,
                        help="每类最多列出 N 条（0=不限，默认 100）")
    p_diff.set_defaults(func=cmd_diff)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
