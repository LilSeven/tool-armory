#!/usr/bin/env python3
r"""timestamp-anomaly — 检测时间戳不合理的文件。

检查项 (输出中给出对应标签):
    future-mtime       修改时间晚于当前时间 (容差 --tolerance-sec, 默认 60 秒)
    future-birth       创建时间晚于当前时间
    future-atime       最后访问时间晚于当前时间
    birth-after-mtime  创建时间比修改时间晚超过 --skew-sec (默认 5 秒)
    negative-mtime     修改时间早于 1970-01-01 (负 epoch)

注意:
    * Windows 上 os.stat().st_ctime 即创建时间; 平台提供 st_birthtime 时优先使用。
    * 复制文件通常保留 mtime 而重置创建时间, birth-after-mtime 对这类文件会报,
      属预期行为; 若误报过多可调大 --skew-sec。

用法:
    python timestamp-anomaly.py <dir> [--tolerance-sec SEC] [--skew-sec SEC]
                                [--summary] [--json] [--follow-links]

示例:
    python timestamp-anomaly.py K:/tmp
    python timestamp-anomaly.py . --skew-sec 3600 --summary
    python timestamp-anomaly.py D:/data --json

退出码: 0 成功(无论是否发现异常); 2 参数错误。
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
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="backslashreplace")
        except Exception:
            pass


def birth_time(st: os.stat_result) -> float:
    """创建时间: 优先 st_birthtime (Python 3.12+), 回退 st_ctime (Windows 上即创建时间)。"""
    bt = getattr(st, "st_birthtime", None)
    if bt is not None:
        return float(bt)
    return float(st.st_ctime)


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


def check_file(st: os.stat_result, now: float, tol: float, skew: float):
    """返回 [(类型, 说明), ...]"""
    issues = []
    mtime = float(st.st_mtime)
    atime = float(st.st_atime)
    btime = birth_time(st)
    if mtime > now + tol:
        issues.append(("future-mtime",
                       f"mtime {iso_local(mtime)} is {(mtime - now) / 86400:.2f} days ahead"))
    if btime > now + tol:
        issues.append(("future-birth",
                       f"birth {iso_local(btime)} is {(btime - now) / 86400:.2f} days ahead"))
    if atime > now + tol:
        issues.append(("future-atime",
                       f"atime {iso_local(atime)} is {(atime - now) / 86400:.2f} days ahead"))
    if btime > mtime + skew:
        issues.append(("birth-after-mtime",
                       f"birth {iso_local(btime)} > mtime {iso_local(mtime)} "
                       f"(by {(btime - mtime) / 86400:.2f} days)"))
    if mtime < 0:
        issues.append(("negative-mtime", f"mtime epoch {mtime} < 0"))
    return issues


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="timestamp-anomaly",
        description="检测时间戳不合理的文件 (mtime 在未来、创建时间晚于修改时间等)。",
    )
    ap.add_argument("dir", help="要扫描的目录")
    ap.add_argument("--tolerance-sec", type=float, default=60.0, metavar="SEC",
                    help="允许“未来”时间戳的容差秒数 (默认 60)")
    ap.add_argument("--skew-sec", type=float, default=5.0, metavar="SEC",
                    help="创建时间与修改时间的允许偏差秒数 (默认 5)")
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
    scanned = 0
    anomalies = []
    counts = {}
    for path, st in iter_files(args.dir, args.follow_links):
        scanned += 1
        for kind, detail in check_file(st, now, args.tolerance_sec, args.skew_sec):
            anomalies.append({"path": path, "type": kind, "detail": detail})
            counts[kind] = counts.get(kind, 0) + 1

    parts = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"

    if args.as_json:
        print(json.dumps({
            "dir": os.path.abspath(args.dir),
            "scanned": scanned,
            "counts": counts,
            "anomalies": anomalies,
        }, ensure_ascii=False, indent=2))
        return 0

    if args.summary:
        print(f"scanned: {scanned} files | anomalies: {len(anomalies)} ({parts})")
        return 0

    for a in anomalies:
        print(f"{a['type']:<18} {a['path']}  ({a['detail']})")
    print(f"-- scanned {scanned} files, {len(anomalies)} anomalies ({parts}) --")
    return 0


if __name__ == "__main__":
    sys.exit(main())
