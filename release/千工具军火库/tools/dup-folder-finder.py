#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重复目录查找器 (dup-folder-finder) —— 找出内容逐文件哈希完全一致的重复文件夹。

用途:
    对目录树中每个文件夹计算内容签名: 其下所有文件的 (相对路径, 大小,
    SHA-256) 有序集合; 每个文件全树只哈希一次。签名相同的文件夹互为完整
    副本, 按组输出并评估哪些可整体删除(每组保留一份), 用于清理重复备份。
    "可删"仅为建议, 本工具绝不执行任何删除。

注意:
    - 只比较普通文件, 符号链接跳过; 空子目录结构差异与文件时间戳不参与判定。
    - 含哈希失败文件(或其子树)的文件夹签名不完整, 不参与分组, 保证零误报。

示例命令:
    python -I dup-folder-finder.py D:/backups
    python -I dup-folder-finder.py D:/backups --min-files 2
    python -I dup-folder-finder.py ./snapshot --json

退出码: 0 正常(无论是否发现重复); 2 参数/路径错误。
仅用 Python 标准库。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys


def force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def hash_file(path: str, algo: str, chunk: int = 1 << 16):
    """分块哈希单个文件, 返回 (hexdigest, 错误信息); 失败时 digest 为 None。"""
    try:
        h = hashlib.new(algo)
        with open(path, "rb") as f:
            while True:
                block = f.read(chunk)
                if not block:
                    break
                h.update(block)
        return h.hexdigest(), None
    except OSError as exc:
        return None, str(exc)


def scan_tree(root: str, algo: str):
    """自底向上为每个文件夹构建内容签名。

    返回 (sigs, tainted, stats, errors):
      sigs:    abs_dir -> tuple((相对posix路径, 大小, 哈希), ...) 已排序
      tainted: abs_dir -> bool, 该目录(或其子树)含无法哈希/判定的内容
      stats:   扫描统计; errors: 错误信息列表
    """
    sigs: dict = {}
    tainted: dict = {}
    stats = {"dirs": 0, "files": 0, "bytes": 0,
             "skipped_symlinks": 0, "hash_errors": 0}
    errors: list = []

    def on_error(exc: OSError) -> None:
        errors.append(str(exc))

    for dirpath, dirnames, filenames in os.walk(root, topdown=False, onerror=on_error):
        stats["dirs"] += 1
        entries = []
        own_fail = False
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                stats["skipped_symlinks"] += 1
                continue
            try:
                st = os.stat(full)
            except OSError as exc:
                errors.append(str(exc))
                own_fail = True
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            digest, err = hash_file(full, algo)
            if digest is None:
                errors.append(f"{full}: {err}")
                own_fail = True
                stats["hash_errors"] += 1
                continue
            entries.append((name.replace(os.sep, "/"), st.st_size, digest))
            stats["files"] += 1
            stats["bytes"] += st.st_size
        child_fail = False
        for d in dirnames:
            child = os.path.join(dirpath, d)
            if os.path.islink(child) or child not in sigs:
                child_fail = True  # 符号链接/无法遍历的子树: 签名不完整
                continue
            prefix = d.replace(os.sep, "/") + "/"
            entries.extend((prefix + rel, size, h) for rel, size, h in sigs[child])
            if tainted.get(child):
                child_fail = True
        entries.sort()
        sigs[dirpath] = tuple(entries)
        tainted[dirpath] = own_fail or child_fail
    return sigs, tainted, stats, errors


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="dup-folder-finder",
        description="找出整目录内容完全相同(逐文件哈希一致)的重复文件夹, 评估可整体删除项。",
    )
    ap.add_argument("root", help="要扫描的目录")
    ap.add_argument("--min-files", type=int, default=1, metavar="N",
                    help="文件夹至少含 N 个文件才参与分组 (默认 1)")
    ap.add_argument("--algo", default="sha256", choices=["sha256", "sha1", "md5"],
                    help="文件哈希算法 (默认 sha256)")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    return ap


def main(argv=None) -> int:
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    root = args.root
    if not os.path.isdir(root):
        print(f"错误: 不是目录或不存在: {root}", file=sys.stderr)
        return 2
    if args.min_files < 0:
        print("错误: --min-files 不能为负数", file=sys.stderr)
        return 2

    sigs, tainted, stats, errors = scan_tree(root, args.algo)

    by_sig: dict = {}
    for abspath, sig in sigs.items():
        if tainted.get(abspath) or len(sig) < args.min_files:
            continue
        by_sig.setdefault(sig, []).append(abspath)
    groups = []
    for sig, members in by_sig.items():
        if len(members) < 2:
            continue
        rels = sorted((os.path.relpath(m, root) for m in members),
                      key=lambda r: (r.count(os.sep), r))  # 越浅的越靠前, 优先保留
        groups.append({
            "members": rels,
            "keep": rels[0],
            "deletable": rels[1:],
            "files": len(sig),
            "bytes": sum(size for _r, size, _h in sig),
        })
    groups.sort(key=lambda g: (-g["files"], -g["bytes"], g["members"][0]))

    # 标注被其他组的祖先目录包含的"可删"成员: 整体删除祖先时它们随之消除
    for g in groups:
        g["contained"] = {}
    for gi, g in enumerate(groups):
        for rel in g["deletable"]:
            containers = sorted({o for gj, h in enumerate(groups) if gj != gi
                                 for o in h["members"]
                                 if rel.startswith(o + os.sep)})
            if containers:
                g["contained"][rel] = containers

    if args.json:
        print(json.dumps({
            "root": os.path.abspath(root),
            "algo": args.algo,
            "min_files": args.min_files,
            "scanned": stats,
            "groups": groups,
            "errors": errors,
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"扫描: {stats['dirs']} 个文件夹 / {stats['files']} 个文件 "
          f"(跳过符号链接 {stats['skipped_symlinks']}, 哈希失败 {stats['hash_errors']})")
    if not groups:
        print("未发现内容完全相同的重复文件夹。")
    else:
        print(f"发现 {len(groups)} 组重复文件夹 (整目录内容逐文件哈希一致):\n")
        for gi, g in enumerate(groups, 1):
            print(f"组 {gi}: {len(g['members'])} 个文件夹, "
                  f"各含 {g['files']} 个文件, 每份 {g['bytes']} 字节")
            print(f"  [保留]  {g['keep']}")
            for rel in g["deletable"]:
                note = f"整体删除可释放 {g['bytes']} 字节"
                c = g["contained"].get(rel)
                if c:
                    note += f"; 已包含在 {'、'.join(c)} 中"
                print(f"  [可删]  {rel}   ({note})")
        print("说明: [可删] 仅为建议, 本工具不会执行任何删除。")
    if errors:
        print(f"警告: {len(errors)} 处无法读取已跳过, 例如: {errors[0]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
