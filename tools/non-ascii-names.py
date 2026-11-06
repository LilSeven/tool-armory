#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""非 ASCII 文件名清单 / non-ascii-names

用途:
    递归扫描目录树, 找出名称中含以下字符的文件/目录, 便于在打包、上传、
    重命名等脚本化处理前排查:
      non-ascii  含非 ASCII 字符(中文、带音符字母、全角符号等)
      space      含空格/制表符等 ASCII 空白
      special    含 ASCII 特殊字符(安全集 [A-Za-z0-9._-] 之外, 如
                 ! # & ' ( ) + , ; = 等命令行/URL 元字符)
      control    含控制字符(资源管理器里不可见, 极易踩坑)
      edge-space 名称首或尾有空白

示例:
    python non-ascii-names.py "K:\data"
    python non-ascii-names.py "K:\data" --only space,special
    python non-ascii-names.py "K:\data" --files-only --json

退出码: 0 = 扫描完成(无论是否命中); 2 = 根目录无效或参数错误。
仅使用 Python 标准库; 输出为 UTF-8; 只读扫描, 不修改任何文件。
"""

import argparse
import json
import os
import string
import sys

SAFE_CHARS = set(string.ascii_letters + string.digits + "._-")
TAG_ORDER = ["non-ascii", "space", "special", "control", "edge-space"]
KNOWN_TAGS = set(TAG_ORDER)


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


def classify(name):
    """返回 (标签集合, 可疑字符列表[按出现顺序去重])。"""
    tags = set()
    bad = []
    for ch in name:
        o = ord(ch)
        if o > 127:
            tag = "non-ascii"
        elif ch.isspace():
            tag = "space"
        elif o < 32 or o == 127:
            tag = "control"
        elif ch not in SAFE_CHARS:
            tag = "special"
        else:
            continue
        tags.add(tag)
        if ch not in bad:
            bad.append(ch)
    if name != name.strip():
        tags.add("edge-space")
    return tags, bad


def fmt_char(ch):
    """单个可疑字符的显示形式: 控制字符/代理对只给码点, 其余带原字符。"""
    o = ord(ch)
    if o < 32 or o == 127 or 0xD800 <= o <= 0xDFFF:
        return f"U+{o:04X}"
    return f"'{ch}'(U+{o:04X})"


def main(argv=None):
    setup_streams()
    parser = argparse.ArgumentParser(
        prog="non-ascii-names",
        description="列出含非 ASCII 字符/空格/特殊字符的文件名与目录名。",
    )
    parser.add_argument("root", nargs="?", default=".",
                        help="要扫描的根目录 (默认: 当前目录)")
    parser.add_argument("--max-depth", type=int, default=None,
                        help="最多下钻层数(根的直接子项为第 1 层), 默认不限")
    parser.add_argument("--only", default=None, metavar="TAG[,TAG...]",
                        help="只看指定标签: " + ",".join(TAG_ORDER))
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--files-only", action="store_true", help="只查文件")
    group.add_argument("--dirs-only", action="store_true", help="只查目录")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)

    if args.only:
        wanted = {t.strip() for t in args.only.split(",") if t.strip()}
        unknown = wanted - KNOWN_TAGS
        if unknown:
            parser.error(f"--only 含未知标签 {sorted(unknown)}; 可选: {','.join(TAG_ORDER)}")
    else:
        wanted = None

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"错误: 根目录不存在或不是目录: {root}", file=sys.stderr)
        return 2

    errors, skipped = [], []
    n_files = n_dirs = 0
    hits = []  # (相对路径, "file"|"dir", 标签集合, 可疑字符列表)
    for dirpath, name, is_dir, _depth in walk_tree(root, args.max_depth, errors, skipped):
        if is_dir:
            n_dirs += 1
        else:
            n_files += 1
        if args.files_only and is_dir:
            continue
        if args.dirs_only and not is_dir:
            continue
        tags, bad = classify(name)
        if not tags:
            continue
        if wanted is not None and not (tags & wanted):
            continue
        rel = os.path.relpath(os.path.join(dirpath, name), root)
        hits.append((rel, "dir" if is_dir else "file", tags, bad))

    tag_count = {}
    for _rel, _typ, tags, _bad in hits:
        for tag in tags:
            tag_count[tag] = tag_count.get(tag, 0) + 1

    def ordered(tags):
        return [t for t in TAG_ORDER if t in tags]

    if args.json:
        payload = {
            "root": root,
            "files": n_files,
            "dirs": n_dirs,
            "hits": len(hits),
            "items": [
                {"path": rel, "type": typ, "tags": ordered(tags),
                 "chars": [fmt_char(c) for c in bad]}
                for rel, typ, tags, bad in hits
            ],
            "tag_summary": {t: tag_count.get(t, 0) for t in TAG_ORDER},
            "errors": [{"path": p, "error": m} for p, m in errors],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"扫描根目录: {root}")
    print(f"条目统计: 文件 {n_files}, 目录 {n_dirs}; 命中 {len(hits)} 条")
    if hits:
        print("命中清单:")
        for i, (rel, typ, tags, bad) in enumerate(hits, 1):
            kind = "目录" if typ == "dir" else "文件"
            chars = ", ".join(fmt_char(c) for c in bad) or "-"
            print(f"  {i:>3}. [{kind}] {rel}")
            print(f"       标签: {', '.join(ordered(tags))}; 可疑字符: {chars}")
    else:
        print("命中清单: (无)")
    print("标签统计(按条目数): "
          + ", ".join(f"{t} {tag_count.get(t, 0)}" for t in TAG_ORDER))
    if errors or skipped:
        print(f"无法访问 {len(errors)} 处; 跳过重复/环形目录 {len(skipped)} 处")
    return 0


if __name__ == "__main__":
    sys.exit(main())
