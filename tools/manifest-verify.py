#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""指纹清单校验器（manifest-verify）。

用途：
    为指定目录生成 SHA-256 指纹清单（manifest JSON），之后可随时校验
    该目录内文件是否被改动（MODIFIED）、缺失（MISSING）或混入新文件（NEW）。
    适用于发布包、备份目录的完整性检查。

用法：
    python -I manifest-verify.py build  <目录> -o <清单.json>
    python -I manifest-verify.py verify <目录> -m <清单.json>

示例（Git Bash / Windows）：
    python -I manifest-verify.py build K:/data/dist -o K:/data/dist.manifest.json
    python -I manifest-verify.py verify K:/data/dist -m K:/data/dist.manifest.json

说明：
    * 清单记录每个文件的相对路径、字节数与 SHA-256；
    * 清单文件本身位于目录内时会被自动跳过，不会计入；
    * 退出码：0=完全一致；1=存在差异；2=参数或 IO 错误。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

CHUNK = 1024 * 1024


def _stdout_utf8() -> None:
    """在 Windows 控制台上尽量用 UTF-8 输出，避免中文乱码或编码报错。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def iter_files(root: str, skip: str | None = None):
    """遍历目录，产出 (相对路径 posix 风格, 绝对路径)；skip 指定要忽略的文件。"""
    skip_abs = os.path.abspath(skip) if skip else None
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            if skip_abs and os.path.abspath(full) == skip_abs:
                continue
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            yield rel, full


def file_digest(path: str) -> tuple[int, str]:
    """流式计算文件大小与 SHA-256，返回 (size, hexdigest)。"""
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        while True:
            block = f.read(CHUNK)
            if not block:
                break
            size += len(block)
            h.update(block)
    return size, h.hexdigest()


def scan(root: str, skip: str | None = None) -> dict:
    files = {}
    for rel, full in iter_files(root, skip=skip):
        size, digest = file_digest(full)
        files[rel] = {"size": size, "sha256": digest}
    return files


def cmd_build(args) -> int:
    root = args.dir
    if not os.path.isdir(root):
        print(f"错误：目录不存在 {root}", file=sys.stderr)
        return 2
    files = scan(root, skip=args.out)
    manifest = {
        "tool": "manifest-verify",
        "algorithm": "sha256",
        "root": os.path.abspath(root),
        "file_count": len(files),
        "files": dict(sorted(files.items())),
    }
    out = args.out
    parent = os.path.dirname(os.path.abspath(out))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
    total = sum(v["size"] for v in files.values())
    print(f"已生成清单：{out}（共 {len(files)} 个文件，合计 {total} 字节）")
    return 0


def cmd_verify(args) -> int:
    root = args.dir
    if not os.path.isdir(root):
        print(f"错误：目录不存在 {root}", file=sys.stderr)
        return 2
    try:
        with open(args.manifest, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"错误：无法读取清单 {args.manifest}: {e}", file=sys.stderr)
        return 2
    recorded = manifest.get("files", {})
    if not isinstance(recorded, dict):
        print(f"错误：清单格式不正确（缺少 files 字典）", file=sys.stderr)
        return 2

    current = scan(root, skip=args.manifest)

    missing = sorted(set(recorded) - set(current))
    added = sorted(set(current) - set(recorded))
    modified = sorted(
        rel
        for rel in set(recorded) & set(current)
        if recorded[rel].get("sha256") != current[rel]["sha256"]
        or recorded[rel].get("size") != current[rel]["size"]
    )

    if not (missing or added or modified):
        print(f"校验通过：{len(current)} 个文件与清单完全一致。")
        return 0

    if missing:
        print(f"[MISSING] 缺失 {len(missing)} 个文件：")
        for rel in missing:
            print(f"  - {rel}")
    if modified:
        print(f"[MODIFIED] 被改动 {len(modified)} 个文件：")
        for rel in modified:
            print(f"  - {rel}")
    if added:
        print(f"[NEW] 混入 {len(added)} 个新文件：")
        for rel in added:
            print(f"  - {rel}")
    matched = len(set(recorded) & set(current)) - len(modified)
    print(
        f"校验失败：缺失 {len(missing)}，改动 {len(modified)}，"
        f"新增 {len(added)}，一致 {matched}。"
    )
    return 1


def main(argv=None) -> int:
    _stdout_utf8()
    p = argparse.ArgumentParser(
        prog="manifest-verify", description="目录文件指纹清单生成与校验工具（SHA-256）"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pb = sub.add_parser("build", help="为目录生成指纹清单")
    pb.add_argument("dir", help="目标目录")
    pb.add_argument("-o", "--out", required=True, help="清单输出路径（JSON）")
    pb.set_defaults(func=cmd_build)

    pv = sub.add_parser("verify", help="校验目录与清单是否一致")
    pv.add_argument("dir", help="目标目录")
    pv.add_argument("-m", "--manifest", required=True, help="清单文件（JSON）")
    pv.set_defaults(func=cmd_verify)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except OSError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
