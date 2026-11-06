#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""空文件查找器 (empty-file-finder) —— 扫描目录树中所有 0 字节文件并按目录汇总。

用途:
    递归扫描指定目录, 找出所有大小为 0 字节的普通文件(跳过符号链接等非
    普通文件), 按所在目录汇总数量, 并标注目录相对扫描根的层级(根目录为
    第 0 层), 便于快速定位同步残留、误建的占位文件或损坏的下载/编译产物。

示例命令:
    python -I empty-file-finder.py D:/data
    python -I empty-file-finder.py ./logs --list          # 额外列出每个空文件
    python -I empty-file-finder.py ./logs --min-level 1   # 只看第 1 层及更深
    python -I empty-file-finder.py ./logs --json          # 机器可读输出

退出码: 0 正常(无论是否找到); 2 参数/路径错误。
仅用 Python 标准库。
"""

from __future__ import annotations

import argparse
import json
import os
import stat
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
    """返回 (per_dir 空文件计数, 空文件相对路径列表, 遍历错误列表)。"""
    per_dir: dict = {}
    empty_files: list = []
    errors: list = []

    def on_error(exc: OSError) -> None:
        errors.append(str(exc))

    for dirpath, _dirnames, filenames in os.walk(root, onerror=on_error):
        count = 0
        for name in filenames:
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full, follow_symlinks=False)
            except OSError as exc:
                errors.append(str(exc))
                continue
            if not stat.S_ISREG(st.st_mode):
                continue  # 符号链接/设备等非普通文件不计入
            if st.st_size == 0:
                count += 1
                empty_files.append(os.path.relpath(full, root))
        if count:
            rel = os.path.relpath(dirpath, root)
            per_dir[rel] = per_dir.get(rel, 0) + count
    return per_dir, empty_files, errors


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="empty-file-finder",
        description="找出目录树中所有 0 字节文件, 按目录汇总数量与所在层级。",
    )
    ap.add_argument("root", help="要扫描的目录")
    ap.add_argument("--list", action="store_true", help="额外列出每个空文件的路径")
    ap.add_argument("--min-level", type=int, default=0, metavar="N",
                    help="只显示层级 >= N 的目录 (默认 0)")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    return ap


def main(argv=None) -> int:
    force_utf8_stdio()
    args = build_parser().parse_args(argv)
    root = args.root
    if not os.path.isdir(root):
        print(f"错误: 不是目录或不存在: {root}", file=sys.stderr)
        return 2

    per_dir, empty_files, errors = scan_tree(root)
    rows = []
    for rel, count in per_dir.items():
        lvl = level_of(rel)
        if lvl >= args.min_level:
            rows.append({"dir": rel, "level": lvl, "count": count})
    rows.sort(key=lambda r: (r["level"], r["dir"]))

    if args.json:
        print(json.dumps({
            "root": os.path.abspath(root),
            "total_empty_files": len(empty_files),
            "dir_count": len(rows),
            "dirs": rows,
            "files": sorted(empty_files),
            "errors": errors,
        }, ensure_ascii=False, indent=2))
        return 0

    if not rows:
        print(f"扫描完成: 未发现 0 字节文件 ({root})")
    else:
        files_by_dir: dict = {}
        for f in empty_files:
            files_by_dir.setdefault(os.path.dirname(f) or ".", []).append(f)
        print("层级  空文件数  目录")
        for r in rows:
            print(f"{r['level']:>4}  {r['count']:>8}  {r['dir']}")
            if args.list:
                for f in sorted(files_by_dir.get(r["dir"], [])):
                    print(f"{'':>4}  {'':>8}    - {f}")
        total = sum(r["count"] for r in rows)
        print(f"合计: {total} 个空文件, 分布在 {len(rows)} 个目录")
    if errors:
        print(f"警告: {len(errors)} 处无法访问已跳过, 例如: {errors[0]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
