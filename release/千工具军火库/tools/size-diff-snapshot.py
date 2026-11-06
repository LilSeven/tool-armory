#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""磁盘占用快照对比 (size-diff-snapshot)

对目录树大小拍 JSON 快照；对比两次快照，输出新增、删除与增长的目录。
目录大小为递归口径(含整个子树)，因此父目录会随子目录一起"增长"。

用法:
    python size-diff-snapshot.py snapshot <目录> -o snap.json
    python size-diff-snapshot.py diff old.json new.json [--min-growth N] [--top 30] [--json]

示例:
    python size-diff-snapshot.py snapshot D:/data -o today.json
    python size-diff-snapshot.py diff yesterday.json today.json --top 20
"""
import argparse
import json
import os
import sys
import unicodedata
from datetime import datetime


def human(n) -> str:
    """字节数 -> 人类可读字符串; 支持负数。"""
    n = float(n)
    neg = n < 0
    n = abs(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if n < 1024 or unit == "PB":
            text = f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
            return ("-" + text) if neg else text
        n /= 1024.0
    return f"{n:,.1f} PB"


def dwidth(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def pad(s: str, width: int) -> str:
    return s + " " * max(0, width - dwidth(s))


def lpad(s: str, width: int) -> str:
    return " " * max(0, width - dwidth(s)) + s


def take_snapshot(root: str) -> dict:
    """拍快照: 返回 {schema, tool, created, root, dirs: {相对路径: 统计}}。

    每个目录记录: own/own_files(直接子文件字节/数) 与 size/files(递归合计)。
    相对路径统一用 / 分隔, 根目录记为 "."。
    """
    root = os.path.abspath(root)
    dirs = {}
    for dirpath, _dirs, names in os.walk(root, onerror=lambda e: None):
        own = 0
        for name in names:
            try:
                own += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
        rel = os.path.relpath(dirpath, root).replace("\\", "/")
        dirs[rel] = {"own": own, "own_files": len(names),
                     "size": own, "files": len(names)}
    # 自底向上把子目录的递归值并入父目录(相对路径按 / 深度从深到浅)
    for rel in sorted(dirs, key=lambda r: -r.count("/")):
        parent = rel.rsplit("/", 1)[0] if "/" in rel else "."
        if parent != rel and parent in dirs:
            dirs[parent]["size"] += dirs[rel]["size"]
            dirs[parent]["files"] += dirs[rel]["files"]
    return {
        "schema": 1,
        "tool": "size-diff-snapshot",
        "created": datetime.now().isoformat(timespec="seconds"),
        "root": os.path.normpath(root),
        "dirs": dirs,
    }


def load_snapshot(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取快照 {path}: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("dirs"), dict):
        raise ValueError(f"不是有效的快照文件: {path}")
    return data


def cmd_snapshot(args) -> int:
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"错误: 不是目录: {root}", file=sys.stderr)
        return 2
    snap = take_snapshot(root)
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        print(f"错误: 无法写入快照: {exc}", file=sys.stderr)
        return 1
    total = snap["dirs"].get(".", {}).get("size",
                                          sum(d.get("size", 0) for d in snap["dirs"].values()))
    print(f"快照已写入: {args.output}")
    print(f"根目录: {snap['root']}    目录数: {len(snap['dirs'])}    总大小: {human(total)}")
    return 0


def cmd_diff(args) -> int:
    try:
        old = load_snapshot(args.old)
        new = load_snapshot(args.new)
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    od, nd = old["dirs"], new["dirs"]
    added = sorted(set(nd) - set(od))
    removed = sorted(set(od) - set(nd))

    grown, shrunk = [], []
    for rel in set(od) & set(nd):
        o_size, n_size = od[rel].get("size", 0), nd[rel].get("size", 0)
        delta = n_size - o_size
        if delta > 0:
            grown.append({"path": rel, "old": o_size, "new": n_size, "delta": delta})
        elif delta < 0:
            shrunk.append({"path": rel, "old": o_size, "new": n_size, "delta": delta})
    grown.sort(key=lambda d: -d["delta"])
    shrunk.sort(key=lambda d: d["delta"])
    grown = [g for g in grown if g["delta"] >= args.min_growth]

    net = (nd.get(".", {}).get("size", 0) - od.get(".", {}).get("size", 0)
           if "." in od and "." in nd else None)

    if args.json:
        print(json.dumps({
            "old": {"file": args.old, "root": old.get("root"),
                    "created": old.get("created")},
            "new": {"file": args.new, "root": new.get("root"),
                    "created": new.get("created")},
            "net_delta": net,
            "added": [{"path": r, "size": nd[r].get("size", 0),
                       "files": nd[r].get("files", 0)} for r in added],
            "removed": [{"path": r, "size": od[r].get("size", 0),
                         "files": od[r].get("files", 0)} for r in removed],
            "grown": grown,
            "shrunk": shrunk,
        }, ensure_ascii=False, indent=2))
        return 0

    if old.get("root") != new.get("root"):
        print(f"[提示] 两次快照根目录不同: {old.get('root')} vs {new.get('root')} (按相对路径对比)")
    print(f"旧快照: {args.old}  ({old.get('created', '?')})")
    print(f"新快照: {args.new}  ({new.get('created', '?')})")
    print()
    net_text = ""
    if net is not None:
        net_text = f"    净增量: {'+' if net >= 0 else ''}{human(net)}"
    print(f"新增目录: {len(added)}    删除目录: {len(removed)}    "
          f"增长目录: {len(grown)}    缩小目录: {len(shrunk)}{net_text}")
    top = max(args.top, 0)
    if added:
        print(f"\n== 新增目录 (显示前 {min(len(added), top) if top else 0}/{len(added)}) ==")
        for r in added[:top]:
            print(f"  {pad(r, 40)}  {human(nd[r].get('size', 0)):>12}")
    if removed:
        print(f"\n== 删除目录 (显示前 {min(len(removed), top) if top else 0}/{len(removed)}) ==")
        for r in removed[:top]:
            print(f"  {pad(r, 40)}  {human(od[r].get('size', 0)):>12}  (原大小)")
    if grown:
        print(f"\n== 增长目录 (显示前 {min(len(grown), top) if top else 0}/{len(grown)}) ==")
        print(f"  {pad('路径', 40)}  {lpad('旧大小', 12)}  {lpad('新大小', 12)}"
              f"  {lpad('增量', 10)}")
        for g in grown[:top]:
            print(f"  {pad(g['path'], 40)}  {human(g['old']):>12}"
                  f"  {human(g['new']):>12}  {'+' + human(g['delta']):>10}")
    if shrunk:
        print(f"\n== 缩小目录 (显示前 {min(len(shrunk), top) if top else 0}/{len(shrunk)}) ==")
        for g in shrunk[:top]:
            print(f"  {pad(g['path'], 40)}  {human(g['old']):>12}"
                  f"  {human(g['new']):>12}  {human(g['delta']):>10}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="size-diff-snapshot",
        description="对目录树大小拍 JSON 快照, 对比两次快照输出新增/删除/增长目录")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_snap = sub.add_parser("snapshot", help="对目录树拍 JSON 快照")
    p_snap.add_argument("root", help="要快照的根目录")
    p_snap.add_argument("-o", "--output", required=True, help="快照 JSON 输出路径")

    p_diff = sub.add_parser("diff", help="对比两次快照")
    p_diff.add_argument("old", help="旧快照 JSON")
    p_diff.add_argument("new", help="新快照 JSON")
    p_diff.add_argument("--min-growth", type=int, default=1, metavar="N",
                        help="增长目录的最小增量字节数(默认 1)")
    p_diff.add_argument("--top", type=int, default=30, metavar="N",
                        help="每节最多显示 N 条(默认 30)")
    p_diff.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    if args.cmd == "snapshot":
        return cmd_snapshot(args)
    return cmd_diff(args)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
