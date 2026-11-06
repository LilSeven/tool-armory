#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日志增长报告（log-growth-report）。

用途：
    对日志目录做大小快照（snapshot 子命令），对比两次快照（report 子
    命令），按增长量从大到小报告增长最快的日志，并标出增长超过阈值的、
    需要轮转（rotate）的日志。

用法：
    python -I log-growth-report.py snapshot <日志目录> -o <快照.json>
    python -I log-growth-report.py report <旧快照.json> <新快照.json>
                                          [--threshold-mb N] [--top N]

示例（Git Bash / Windows）：
    python -I log-growth-report.py snapshot K:/logs -o K:/snap/old.json
    python -I log-growth-report.py snapshot K:/logs -o K:/snap/new.json
    python -I log-growth-report.py report K:/snap/old.json K:/snap/new.json --threshold-mb 100

说明：
    * 快照只记录相对路径、大小与 mtime，不读取文件内容；
    * 两次快照之间消失的文件单独列出（视为释放空间）；
    * 退出码：0=成功；2=参数或 IO 错误。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

SNAPSHOT_TAG = "log-growth-report-snapshot"


def _stdout_utf8() -> None:
    """在 Windows 控制台上尽量用 UTF-8 输出，避免中文乱码或编码报错。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def human_size(n: int) -> str:
    v = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(v)} B"
            return f"{v:.1f} {unit}"
        v /= 1024
    return f"{v:.1f} TB"


def _walk_sizes(root: str) -> dict:
    files = {}
    for dirpath, _dirs, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            files[rel] = {"size": st.st_size, "mtime": int(st.st_mtime)}
    return files


def cmd_snapshot(args) -> int:
    root = args.dir
    if not os.path.isdir(root):
        print(f"错误：目录不存在 {root}", file=sys.stderr)
        return 2
    files = _walk_sizes(root)
    snap = {
        "tool": SNAPSHOT_TAG,
        "taken_at": datetime.now().isoformat(timespec="seconds"),
        "dir": os.path.abspath(root),
        "file_count": len(files),
        "total_size": sum(v["size"] for v in files.values()),
        "files": files,
    }
    out = args.out
    parent = os.path.dirname(os.path.abspath(out))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(
        f"快照已保存：{out}（目录 {snap['dir']}，文件 {len(files)} 个，"
        f"合计 {human_size(snap['total_size'])}）"
    )
    return 0


def _load_snapshot(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("tool") != SNAPSHOT_TAG or not isinstance(data.get("files"), dict):
        raise ValueError(f"不是有效的快照文件：{path}")
    return data


def cmd_report(args) -> int:
    try:
        old = _load_snapshot(args.old)
        new = _load_snapshot(args.new)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2

    threshold = args.threshold_mb * 1024 * 1024
    old_files = old["files"]
    new_files = new["files"]

    rows = []  # (growth, rel, old_size, new_size, category)
    deleted = []  # (old_size, rel)
    for rel in sorted(set(old_files) | set(new_files)):
        o = old_files.get(rel, {}).get("size")
        n = new_files.get(rel, {}).get("size")
        if o is None:
            rows.append((n, rel, 0, n, "新增"))
        elif n is None:
            deleted.append((o, rel))
        else:
            g = n - o
            cat = "增长" if g > 0 else ("持平" if g == 0 else "缩小")
            rows.append((g, rel, o, n, cat))
    rows.sort(key=lambda t: (-t[0], t[1]))

    total_old = sum(v["size"] for v in old_files.values())
    total_new = sum(v["size"] for v in new_files.values())
    delta = total_new - total_old

    print("对比快照：")
    print(
        f"  旧: {args.old}（{old.get('taken_at', '?')}，目录 {old.get('dir', '?')}，"
        f"{old.get('file_count', len(old_files))} 个文件，合计 {human_size(total_old)}）"
    )
    print(
        f"  新: {args.new}（{new.get('taken_at', '?')}，目录 {new.get('dir', '?')}，"
        f"{new.get('file_count', len(new_files))} 个文件，合计 {human_size(total_new)}）"
    )
    print(f"总体增长: {delta:+,} 字节（{human_size(abs(delta))}）")

    shown = rows[: args.top]
    if shown:
        print(f"\n增长最快 Top {len(shown)}:")
        for g, rel, o, n, cat in shown:
            if cat == "新增":
                print(f"  {human_size(max(g, 0)):>10}  {rel}  （新增文件，现 {human_size(n)}）")
            else:
                pct = f"{g / o * 100:+.1f}%" if o else "N/A"
                print(f"  {g:+,} 字节  {rel}  {human_size(o)} -> {human_size(n)}（{pct}，{cat}）")
    else:
        print("\n（无可对比文件）")

    rotate = [(g, rel) for g, rel, _o, _n, cat in rows if g >= threshold and cat in ("增长", "新增")]
    if rotate:
        print(f"\n需要轮转（增长 >= {args.threshold_mb:g} MB）: {len(rotate)} 个")
        for g, rel in rotate:
            print(f"  - {rel}  +{human_size(g)}")
    else:
        print(f"\n需要轮转（增长 >= {args.threshold_mb:g} MB）: 无")

    if deleted:
        print(f"\n已消失/被清理 {len(deleted)} 个文件:")
        for o, rel in deleted[: args.top]:
            print(f"  - {rel}（释放 {human_size(o)}）")
    return 0


def main(argv=None) -> int:
    _stdout_utf8()
    p = argparse.ArgumentParser(
        prog="log-growth-report", description="日志目录大小快照与两次快照的增长对比报告"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("snapshot", help="记录日志目录当前大小快照")
    ps.add_argument("dir", help="日志目录")
    ps.add_argument("-o", "--out", required=True, help="快照输出路径（JSON）")
    ps.set_defaults(func=cmd_snapshot)

    pr = sub.add_parser("report", help="对比两个快照，报告增长与需要轮转的日志")
    pr.add_argument("old", help="旧快照（JSON）")
    pr.add_argument("new", help="新快照（JSON）")
    pr.add_argument("--threshold-mb", type=float, default=10.0,
                    help="增长阈值（MB），达到即提示轮转（默认 10）")
    pr.add_argument("--top", type=int, default=10, help="显示增长前 N 名（默认 10）")
    pr.set_defaults(func=cmd_report)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except OSError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
