#!/usr/bin/env python3
r"""age-buckets — 按未修改天数分桶 (7 天/30 天/1 年…), 统计各桶文件数与占用空间。

以指定时间字段距今的天数把文件分入各桶: [0,b1), [b1,b2), ..., [bn,∞)。
默认桶边界: 7d,30d,90d,1y,3y。单位: d=天, w=周, m=月(按 30 天), y=年(按 365 天)。
--field 可选 mtime(默认)/atime/ctime; Windows 上 ctime 为创建时间,
POSIX 上 ctime 为元数据变更时间。mtime 在未来的文件落入第一桶。

用法:
    python age-buckets.py <dir> [--field mtime|atime|ctime]
                          [--buckets "7d,30d,90d,1y,3y"] [--json] [--follow-links]

示例:
    python age-buckets.py K:/tmp
    python age-buckets.py . --buckets "7d,30d,1y" --field atime
    python age-buckets.py D:/data --json

退出码: 0 成功; 2 参数错误。
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
import re
import stat as stat_mod
import sys
import time

FIELD_ATTR = {"mtime": "st_mtime", "atime": "st_atime", "ctime": "st_ctime"}
UNIT_DAYS = {"d": 1.0, "w": 7.0, "m": 30.0, "y": 365.0}
DEFAULT_BUCKETS = "7d,30d,90d,1y,3y"
BUCKET_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*([dwmy])$")


def fix_streams() -> None:
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


def fmt_days(d: float) -> str:
    if d >= 365:
        return f"{d / 365.0:g}y"
    return f"{d:g}d"


def parse_buckets(spec: str):
    """'7d,30d,1y' -> [7.0, 30.0, 365.0]"""
    bounds = []
    for tok in spec.split(","):
        tok = tok.strip().lower()
        if not tok:
            continue
        m = BUCKET_RE.fullmatch(tok)
        if not m:
            raise ValueError(f"bad bucket token: {tok!r} (use like 7d / 2w / 6m / 1y)")
        bounds.append(float(m.group(1)) * UNIT_DAYS[m.group(2)])
    if not bounds:
        raise ValueError("empty bucket spec")
    for a, b in zip(bounds, bounds[1:]):
        if b <= a:
            raise ValueError("bucket bounds must be strictly increasing")
    return bounds


def bucket_labels(bounds):
    labels = []
    prev = 0.0
    for b in bounds:
        labels.append(f"0-{fmt_days(b)}" if prev == 0 else f"{fmt_days(prev)}-{fmt_days(b)}")
        prev = b
    labels.append(f"{fmt_days(bounds[-1])}+")
    return labels


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="age-buckets",
        description="按未修改天数分桶 (7 天/30 天/1 年…), 统计各桶文件数与占用空间。",
    )
    ap.add_argument("dir", help="要扫描的目录")
    ap.add_argument("--field", choices=("mtime", "atime", "ctime"), default="mtime",
                    help="按哪个时间字段计算“年龄” (默认 mtime)")
    ap.add_argument("--buckets", default=DEFAULT_BUCKETS, metavar="SPEC",
                    help='逗号分隔的桶边界, 如 "7d,30d,90d,1y,3y"')
    ap.add_argument("--json", dest="as_json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--follow-links", action="store_true", help="跟随符号链接目录")
    return ap


def main(argv=None) -> int:
    fix_streams()
    args = build_parser().parse_args(argv)
    if not os.path.isdir(args.dir):
        print(f"error: not a directory: {args.dir}", file=sys.stderr)
        return 2
    try:
        bounds = parse_buckets(args.buckets)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    labels = bucket_labels(bounds)
    attr = FIELD_ATTR[args.field]
    now = time.time()
    counts = [0] * (len(bounds) + 1)
    sizes = [0] * (len(bounds) + 1)
    scanned = 0
    for dirpath, _dirs, names in os.walk(args.dir, followlinks=args.follow_links):
        for name in names:
            path = os.path.join(dirpath, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            if not stat_mod.S_ISREG(st.st_mode):
                continue
            scanned += 1
            age_days = (now - float(getattr(st, attr))) / 86400.0
            idx = bisect.bisect_right(bounds, age_days)  # age<0 (未来) 落入第 0 桶
            counts[idx] += 1
            sizes[idx] += st.st_size

    total_files = sum(counts)
    total_bytes = sum(sizes)

    if args.as_json:
        buckets = []
        for i, lab in enumerate(labels):
            buckets.append({
                "label": lab,
                "files": counts[i],
                "bytes": sizes[i],
                "share_bytes": round(sizes[i] / total_bytes, 4) if total_bytes else 0.0,
            })
        print(json.dumps({
            "dir": os.path.abspath(args.dir),
            "field": args.field,
            "buckets_spec": args.buckets,
            "scanned": scanned,
            "total_files": total_files,
            "total_bytes": total_bytes,
            "buckets": buckets,
        }, ensure_ascii=False, indent=2))
        return 0

    w = max(max((len(l) for l in labels), default=5), len("TOTAL"))
    print(f"{'bucket':<{w}}  {'files':>6}  {'bytes':>15}  {'share':>7}  {'human':>10}")
    for i, lab in enumerate(labels):
        share = sizes[i] / total_bytes * 100 if total_bytes else 0.0
        print(f"{lab:<{w}}  {counts[i]:>6}  {sizes[i]:>15,}  "
              f"{share:>6.1f}%  {human_size(sizes[i]):>10}")
    print(f"{'TOTAL':<{w}}  {total_files:>6}  {total_bytes:>15,}  "
          f"{'100.0%':>7}  {human_size(total_bytes):>10}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
