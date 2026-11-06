#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Unicode 规范化检查 / unicode-normalize-check

用途:
    检测文件名/目录名的 Unicode 规范化形式(NFC/NFD)不一致:
      1) 名称本身不是 NFC 形式 —— 多为 macOS 拷来的 NFD 名称(如
         "cafe"+U+0301 组合音符), 脚本里按 NFC 书写的名字会匹配不到;
      2) 同一目录下"看起来一样、底层编码不同"的名称组 —— 例如 NFC 的
         "café.txt" 与 NFD 的 "cafe\u0301.txt", 两者可以同时存在,
         肉眼无法区分, 容易打开/覆盖错文件。

    输出中组合记号等不可见字符一律以 \uXXXX 转义显示, 便于肉眼对比。

示例:
    python unicode-normalize-check.py "K:\data"
    python unicode-normalize-check.py "K:\data" --form NFD   # 以 NFD 为目标形式
    python unicode-normalize-check.py "K:\data" --json

退出码: 0 = 扫描完成(无论是否发现); 2 = 根目录无效或参数错误。
仅使用 Python 标准库; 输出为 UTF-8; 只读扫描, 不修改任何文件。
"""

import argparse
import json
import os
import sys
import unicodedata


def setup_streams():
    """让 stdout/stderr 以 UTF-8 输出, 避免中文/特殊字符在 Windows 控制台报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def walk_tree(root, max_depth=None, errors=None, skipped=None):
    """先序遍历目录树, 逐条 yield (dirpath, name, is_dir, depth)。

    - 根的直接子项 depth=0; max_depth 限制下钻层数(None 不限);
    - 目录内条目按名称排序, 输出顺序确定;
    - 符号链接/目录联接不跟随; realpath 已访问过的目录跳过(防环);
    - 无权限等 OSError 记入 errors 列表后继续, 不中断整体扫描。
    """
    stack = [(root, 0)]
    seen = set()
    while stack:
        cur, depth = stack.pop()
        try:
            real = os.path.realpath(cur)
        except OSError:
            real = cur
        if real in seen:
            if skipped is not None:
                skipped.append(cur)
            continue
        seen.add(real)
        try:
            with os.scandir(cur) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as exc:
            if errors is not None:
                errors.append((cur, str(exc)))
            continue
        subdirs = []
        for ent in entries:
            try:
                is_dir = ent.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False
            yield cur, ent.name, is_dir, depth
            if is_dir and (max_depth is None or depth + 1 <= max_depth):
                subdirs.append((os.path.join(cur, ent.name), depth + 1))
        for sub in reversed(subdirs):
            stack.append(sub)


def name_form(name):
    """判定名称的规范化形态: NFC / NFD / MIXED(既非纯 NFC 也非纯 NFD)。"""
    if name == unicodedata.normalize("NFC", name):
        return "NFC"
    if name == unicodedata.normalize("NFD", name):
        return "NFD"
    return "MIXED"


def visible(text):
    """组合记号/控制字符/代理对等以 \\uXXXX 显示, 其余字符原样保留。"""
    out = []
    for ch in text:
        if unicodedata.category(ch).startswith(("M", "C")):
            out.append("\\u%04X" % ord(ch))
        else:
            out.append(ch)
    return "".join(out)


def main(argv=None):
    setup_streams()
    parser = argparse.ArgumentParser(
        prog="unicode-normalize-check",
        description='检测 NFC/NFD 规范化不一致造成的"看起来相同"文件名。',
    )
    parser.add_argument("root", nargs="?", default=".",
                        help="要扫描的根目录 (默认: 当前目录)")
    parser.add_argument("--form", choices=("NFC", "NFD"), default="NFC",
                        help="目标规范化形式, 默认 %(default)s")
    parser.add_argument("--max-depth", type=int, default=None,
                        help="最多下钻层数(根的直接子项为第 1 层), 默认不限")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)
    target = args.form

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"错误: 根目录不存在或不是目录: {root}", file=sys.stderr)
        return 2

    errors, skipped = [], []
    n_files = n_dirs = 0
    non_target = []  # (相对路径, "file"|"dir", 形态, 原名)
    by_key = {}      # 目录 -> {规范化键: [(原名, 形态), ...]}
    for dirpath, name, is_dir, _depth in walk_tree(root, args.max_depth, errors, skipped):
        if is_dir:
            n_dirs += 1
        else:
            n_files += 1
        form = name_form(name)
        if form != target:
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            non_target.append((rel, "dir" if is_dir else "file", form, name))
        key = unicodedata.normalize(target, name)
        by_key.setdefault(dirpath, {}).setdefault(key, []).append((name, form))

    groups = []  # (目录, [(原名, 形态), ...])
    for dirpath in sorted(by_key):
        for key in sorted(by_key[dirpath]):
            items = by_key[dirpath][key]
            if len({raw for raw, _f in items}) > 1:
                ordered = sorted(items, key=lambda t: (t[1] != target, t[0]))
                groups.append((dirpath, ordered))

    def rel_dir(d):
        return "." if d == root else os.path.relpath(d, root)

    if args.json:
        payload = {
            "root": root,
            "target_form": target,
            "files": n_files,
            "dirs": n_dirs,
            "non_target_count": len(non_target),
            "non_target": [
                {"path": rel, "type": typ, "form": form, "display": visible(name)}
                for rel, typ, form, name in non_target[:50]
            ],
            "group_count": len(groups),
            "groups": [
                {"dir": visible(rel_dir(d)),
                 "items": [{"name": raw, "form": f, "display": visible(raw)}
                           for raw, f in items]}
                for d, items in groups
            ],
            "errors": [{"path": p, "error": m} for p, m in errors],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"扫描根目录: {root}")
    print(f"条目统计: 文件 {n_files}, 目录 {n_dirs} (目标形式: {target})")
    print()
    if non_target:
        print(f"非 {target} 形式的名称: 共 {len(non_target)} 条, 最多显示 50 条:")
        for rel, typ, form, name in non_target[:50]:
            print(f"  [{form:<5}] {visible(rel)}")
    else:
        print(f"非 {target} 形式的名称: 无")
    print()
    if groups:
        print(f'"看起来相同"的名称组: 共 {len(groups)} 组:')
        for d, items in groups:
            print(f"  目录: {visible(rel_dir(d))}")
            for raw, form in items:
                print(f"    [{form:<5}] {visible(raw)}")
    else:
        print('"看起来相同"的名称组: 无')
    print()
    print(f"汇总: 非 {target} 名称 {len(non_target)} 条; 相同名组 {len(groups)} 组。")
    print("说明: 名称按目标形式规范化后相同即归为一组; 组合记号以 \\uXXXX 显示。")
    if errors or skipped:
        print(f"无法访问 {len(errors)} 处; 跳过重复/环形目录 {len(skipped)} 处")
    return 0


if __name__ == "__main__":
    sys.exit(main())
