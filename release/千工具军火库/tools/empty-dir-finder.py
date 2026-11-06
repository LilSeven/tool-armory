#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""空目录查找器 (empty-dir-finder) —— 自底向上找出空目录(含删空子目录后变空的)。

用途:
    递归扫描目录树, 自底向上判断哪些目录是空目录: 既包括本来就没有任何
    文件的目录, 也包括"所有子目录都是空目录(删除后自己随之变空)"的级联
    空目录。默认只列出不删除; 确认后追加 --delete 才会从最深层开始逐个
    rmdir 删除(只删空目录, 绝不删除文件)。

示例命令:
    python -I empty-dir-finder.py D:/data              # 只列出空目录
    python -I empty-dir-finder.py D:/data --json       # 机器可读输出
    python -I empty-dir-finder.py D:/data --delete     # 真正删除(先跑一次确认!)

退出码: 0 正常; 1 --delete 时有目录删除失败; 2 参数/路径错误。
仅用 Python 标准库。
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def force_utf8_stdio() -> None:
    """Windows 控制台默认编码可能打不出中文, 统一切到 UTF-8(失败则忽略)。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def level_of(rel_dir: str) -> int:
    """目录相对扫描根的层级: 根目录本身为 0, 其直接子目录为 1, 以此类推。"""
    if rel_dir == ".":
        return 0
    return rel_dir.count(os.sep) + 1


def scan_tree(root: str):
    """自底向上判定空目录。

    返回 (info, errors):
      info: abs_dir -> {"empty": bool, "kind": "empty"|"cascade",
                        "children": [直接的空子目录 abs 路径]}
      errors: 遍历错误字符串列表
    说明: 符号链接目录、无法访问的子目录一律保守视为"非空", 不会被删除。
    """
    info: dict = {}
    errors: list = []

    def on_error(exc: OSError) -> None:
        errors.append(str(exc))

    for dirpath, dirnames, filenames in os.walk(root, topdown=False, onerror=on_error):
        blocked = False
        empty_children = []
        for d in dirnames:
            child = os.path.join(dirpath, d)
            if os.path.islink(child) or child not in info:
                blocked = True  # 无法判定的子目录: 保守处理
            elif info[child]["empty"]:
                empty_children.append(child)
        all_children_empty = (not blocked) and len(empty_children) == len(dirnames)
        is_empty = (not filenames) and all_children_empty
        info[dirpath] = {
            "empty": is_empty,
            "kind": "empty" if not dirnames else "cascade",
            "children": empty_children,
        }
    return info, errors


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="empty-dir-finder",
        description="自底向上找出空目录(含删空子目录后变空的), 默认只列出不删除。",
    )
    ap.add_argument("root", help="要扫描的目录")
    ap.add_argument("--delete", action="store_true",
                    help="真正删除列出的空目录(默认仅列出)")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    return ap


def main(argv=None) -> int:
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    root = args.root
    if not os.path.isdir(root):
        print(f"错误: 不是目录或不存在: {root}", file=sys.stderr)
        return 2

    info, errors = scan_tree(root)
    rows = []
    for p, v in info.items():
        if not v["empty"]:
            continue
        rel = os.path.relpath(p, root)
        rows.append({
            "dir": rel,
            "level": level_of(rel),
            "kind": v["kind"],
            "children": [os.path.relpath(c, root) for c in v["children"]],
        })
    rows.sort(key=lambda r: (-r["level"], r["dir"]))  # 自底向上: 最深的先列出

    deleted, delete_errors = [], []

    if args.json:
        print(json.dumps({
            "root": os.path.abspath(root),
            "empty_dir_count": len(rows),
            "dirs": rows,
            "deleted": deleted,
            "delete_errors": delete_errors,
            "errors": errors,
        }, ensure_ascii=False, indent=2))
        if args.delete:
            for r in rows:
                target = root if r["dir"] == "." else os.path.join(root, r["dir"])
                try:
                    os.rmdir(target)
                    deleted.append(r["dir"])
                except OSError as exc:
                    delete_errors.append(f"{r['dir']}: {exc}")
            if delete_errors:
                return 1
        return 0

    if not rows:
        print(f"扫描完成: 未发现空目录 ({root})")
    else:
        print("层级  类型    目录")
        for r in rows:
            kind = "空目录" if r["kind"] == "empty" else "级联空"
            note = ""
            if r["kind"] == "cascade" and r["children"]:
                note = f"   (删空 {'、'.join(r['children'])} 后变空)"
            print(f"{r['level']:>4}  {kind:<6}  {r['dir']}{note}")
        n_leaf = sum(1 for r in rows if r["kind"] == "empty")
        n_cascade = len(rows) - n_leaf
        print(f"共 {len(rows)} 个空目录 (本级为空 {n_leaf}, 级联变空 {n_cascade})")

    if args.delete:
        for r in rows:
            target = root if r["dir"] == "." else os.path.join(root, r["dir"])
            try:
                os.rmdir(target)
                deleted.append(r["dir"])
                print(f"已删除: {r['dir']}")
            except OSError as exc:
                delete_errors.append(f"{r['dir']}: {exc}")
                print(f"删除失败: {r['dir']} ({exc})", file=sys.stderr)
        print(f"删除完成: 成功 {len(deleted)}, 失败 {len(delete_errors)}")
        if delete_errors:
            return 1
    else:
        print("(默认仅列出, 未删除任何目录; 确认后加 --delete 执行删除)")
    if errors:
        print(f"警告: {len(errors)} 处无法访问已跳过, 例如: {errors[0]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
