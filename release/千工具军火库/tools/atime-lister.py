#!/usr/bin/env python3
r"""atime-lister — 按最后访问时间 (atime) 排序/筛选文件, 找出长期无人读取的文件。

用法:
    python atime-lister.py <dir> [--older-than DAYS] [--newer-than DAYS]
                           [--sort atime|size|path] [--desc] [--limit N]
                           [--summary] [--json] [--follow-links]

说明:
    递归扫描目录, 依据 os.stat().st_atime 计算每个文件距上次访问的天数。
    注意: 结果依赖文件系统是否记录 atime (Windows 系统盘/部分挂载默认关闭
    访问时间更新, 此时 atime 可能等于创建时间或修改时间)。

示例:
    python atime-lister.py K:/tmp --older-than 30 --limit 20
    python atime-lister.py . --sort size --desc --summary
    python atime-lister.py D:/data --older-than 90 --json

退出码: 0 成功; 2 参数错误。
"""

from __future__ import annotations

import argparse
import json
import os
import stat as stat_mod
import sys
import time
from datetime import datetime


def fix_streams() -> None:
    """重定向输出时避免特殊字符触发 UnicodeEncodeError。"""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="backslashreplace")
        except Exception:
            pass


def human_size(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024 or unit == "PB":
            return f"{n:.0f} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def iso_local(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return "out-of-range"


def iter_files(root: str, follow: bool):
    for dirpath, _dirs, names in os.walk(root, followlinks=follow):
        for name in names:
            path = os.path.join(dirpath, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            if stat_mod.S_ISREG(st.st_mode):
                yield path, st


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="atime-lister",
        description="按最后访问时间 (atime) 排序/筛选文件, 找出长期无人读取的文件。",
    )
    ap.add_argument("dir", help="要扫描的目录")
    ap.add_argument("--older-than", type=float, metavar="DAYS",
                    help="只列出 atime 距今超过 DAYS 天的文件")
    ap.add_argument("--newer-than", type=float, metavar="DAYS",
                    help="只列出 atime 距今不足 DAYS 天的文件")
    ap.add_argument("--sort", choices=("atime", "size", "path"), default="atime",
                    help="排序字段 (默认 atime, 即最久未访问在前)")
    ap.add_argument("--desc", action="store_true", help="降序排列")
    ap.add_argument("--limit", type=int, metavar="N", help="最多输出 N 个文件")
    ap.add_argument("--summary", action="store_true", help="只输出统计摘要")
    ap.add_argument("--json", dest="as_json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--follow-links", action="store_true", help="跟随符号链接目录")
    return ap


def main(argv=None) -> int:
    fix_streams()
    args = build_parser().parse_args(argv)
    if not os.path.isdir(args.dir):
        print(f"error: not a directory: {args.dir}", file=sys.stderr)
        return 2

    now = time.time()
    rows = []
    scanned = 0
    for path, st in iter_files(args.dir, args.follow_links):
        scanned += 1
        age_days = (now - st.st_atime) / 86400.0
        if args.older_than is not None and age_days < args.older_than:
            continue
        if args.newer_than is not None and age_days > args.newer_than:
            continue
        rows.append({
            "path": path,
            "atime": st.st_atime,
            "age_days": round(age_days, 3),
            "size": st.st_size,
        })

    keymap = {
        "atime": lambda r: r["atime"],
        "size": lambda r: r["size"],
        "path": lambda r: r["path"].lower(),
    }
    rows.sort(key=keymap[args.sort], reverse=args.desc)
    total_size = sum(r["size"] for r in rows)
    shown = rows if args.limit is None else rows[: max(args.limit, 0)]

    if args.as_json:
        payload = {
            "dir": os.path.abspath(args.dir),
            "scanned": scanned,
            "matched": len(rows),
            "total_size": total_size,
            "files": [{**r, "atime_iso": iso_local(r["atime"])} for r in shown],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.summary:
        print(f"scanned: {scanned} files | matched: {len(rows)} | "
              f"total size: {human_size(total_size)}")
        if rows:
            oldest = min(rows, key=lambda r: r["atime"])
            newest = max(rows, key=lambda r: r["atime"])
            print(f"oldest atime: {iso_local(oldest['atime'])}  {oldest['path']}")
            print(f"newest atime: {iso_local(newest['atime'])}  {newest['path']}")
        else:
            print("no files matched")
        return 0

    for r in shown:
        print(f"{iso_local(r['atime'])}  {human_size(r['size']):>10}  {r['path']}")
    print(f"-- shown {len(shown)}/{len(rows)} matched (scanned {scanned}), "
          f"total {human_size(total_size)} --")
    return 0


if __name__ == "__main__":
    sys.exit(main())
