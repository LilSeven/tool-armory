#!/usr/bin/env python3
"""du-json-export —— 机器可读的目录占用输出。

以 JSON 输出目录树的大小结构（du 风格的文件总字节数），供 jq 等脚本工具继续消费:

    目录节点: {"name","type":"dir","size":总字节,"files":文件数,"dirs":子目录数,"children":[...]}
    文件节点: {"name","type":"file","size":字节数}

符号链接不跟随；无权限等错误写入 stderr 并在对应节点记 "error" 字段，
stdout 始终只输出一份完整 JSON，可直接接管道。

用法:
    python du-json-export.py <目录> [选项]

选项:
    --depth N        限制展开的子目录层数（0 = 不限制，默认 0；被截断的节点标 "truncated":true）
    --dirs-only      子节点只列目录，不列文件（大小仍统计全部文件）
    --sort MODE      子节点排序: name | size-desc | size-asc，默认 name

示例:
    python du-json-export.py D:/data | jq '.size'
    python du-json-export.py D:/data --depth 1 --dirs-only | jq '.children[].name'
    python du-json-export.py D:/data --sort size-desc | jq -r '.children[] | "\\(.name) \\(.size)"'

退出码: 0 = 成功（个别子目录读不了不影响）；2 = 目录不存在等用法错误。
仅使用 Python 标准库。
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def scan_tree(path: str, name: str, dirs_only: bool, errors: list) -> dict:
    node = {"name": name, "type": "dir", "size": 0, "files": 0, "dirs": 0}
    children = []
    try:
        with os.scandir(path) as iterator:
            entries = sorted(iterator, key=lambda e: e.name)
    except OSError as exc:
        node["error"] = str(exc)
        errors.append(f"{path}: {exc}")
        return node
    for entry in entries:
        try:
            if entry.is_dir(follow_symlinks=False):
                sub = scan_tree(entry.path, entry.name, dirs_only, errors)
                node["size"] += sub["size"]
                node["files"] += sub["files"]
                node["dirs"] += sub["dirs"] + 1
                children.append(sub)
            elif entry.is_file(follow_symlinks=False):
                size = entry.stat(follow_symlinks=False).st_size
                node["size"] += size
                node["files"] += 1
                if not dirs_only:
                    children.append({"name": entry.name, "type": "file", "size": size})
            else:
                size = entry.stat(follow_symlinks=False).st_size
                node["size"] += size
                if not dirs_only:
                    children.append({"name": entry.name, "type": "special", "size": size})
        except OSError as exc:
            errors.append(f"{entry.path}: {exc}")
    node["children"] = children
    return node


def apply_depth(node: dict, depth: int, max_depth) -> None:
    """超过 max_depth 的目录不再输出 children（大小仍为整棵子树的统计）。"""
    if node.get("type") != "dir":
        return
    children = node.get("children", [])
    if max_depth is not None and depth >= max_depth:
        if children:
            node["truncated"] = True
        node.pop("children", None)
        return
    for child in children:
        apply_depth(child, depth + 1, max_depth)


def sort_children(node: dict, mode: str) -> None:
    children = node.get("children")
    if not children:
        return
    for child in children:
        sort_children(child, mode)
    if mode == "name":
        children.sort(key=lambda c: c["name"])
    elif mode == "size-desc":
        children.sort(key=lambda c: (-c["size"], c["name"]))
    else:
        children.sort(key=lambda c: (c["size"], c["name"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="du-json-export",
        description="以 JSON 输出目录树大小结构（du 风格），供 jq 等脚本继续消费。",
    )
    parser.add_argument("root", help="要统计的目录")
    parser.add_argument("--depth", type=int, default=0, metavar="N",
                        help="限制展开的子目录层数（0 = 不限制，默认 0）")
    parser.add_argument("--dirs-only", action="store_true",
                        help="子节点只列目录，不列文件（大小仍统计全部文件）")
    parser.add_argument("--sort", choices=("name", "size-desc", "size-asc"),
                        default="name", help="子节点排序方式，默认按名称")
    args = parser.parse_args(argv)

    root = args.root
    if not os.path.isdir(root):
        print(f"错误: 不是目录或不存在: {root}", file=sys.stderr)
        return 2

    max_depth = args.depth if args.depth > 0 else None
    errors: list = []
    tree = scan_tree(root, os.path.basename(os.path.abspath(root)) or root,
                     args.dirs_only, errors)
    tree = {"path": root, **tree}
    apply_depth(tree, 0, max_depth)
    sort_children(tree, args.sort)

    for err in errors:
        print(f"警告: {err}", file=sys.stderr)
    try:
        print(json.dumps(tree, ensure_ascii=False, indent=2))
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    _force_utf8_stdio()
    sys.exit(main())
