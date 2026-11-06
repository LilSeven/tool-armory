#!/usr/bin/env python3
r"""epoch-converter — 以人类可读格式输出文件时间戳, 并支持按时间范围筛选文件列表。

三种用法:
  1) epoch/日期互转 (直接传参数: 纯数字视为 epoch 秒, 超大数字视为毫秒,
     非数字视为 ISO 本地日期时间):
       python epoch-converter.py 1600000000 1700000000
       python epoch-converter.py 2024-06-01 "2024-06-01 12:00:00"
  2) 列出目录内文件的时间戳 (--field 选择 mtime/atime/ctime, 默认 mtime):
       python epoch-converter.py --dir K:/tmp --field mtime --relative
  3) 按时间范围筛选文件 (--after/--before 接受 epoch 或 "YYYY-MM-DD[ HH:MM:SS]"
     本地时间; --before 为纯日期时自动取当天 23:59:59):
       python epoch-converter.py --dir K:/tmp --after 2024-06-01 --before "2024-06-30"

选项:
    --format FMT   strftime 格式 (默认 "%Y-%m-%d %H:%M:%S")
    --relative     附加距今时长; --limit N 限制输出行数; --desc 降序; --json 输出 JSON

退出码: 0 成功; 2 参数/时间解析错误。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat as stat_mod
import sys
import time
from datetime import datetime, timezone

DEFAULT_FMT = "%Y-%m-%d %H:%M:%S"
NUM_RE = re.compile(r"^-?\d+$")
DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FIELD_ATTR = {"mtime": "st_mtime", "atime": "st_atime", "ctime": "st_ctime"}


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


def parse_when(text: str):
    """返回 (epoch 秒, 类型, 是否纯日期)。类型: epoch | epoch-ms | local | aware。"""
    t = text.strip()
    if NUM_RE.fullmatch(t):
        v = int(t)
        if abs(v) >= 10 ** 12:  # 毫秒级时间戳
            return v / 1000.0, "epoch-ms", False
        return float(v), "epoch", False
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        raise ValueError(
            f"cannot parse time: {text!r} "
            f"(expect epoch seconds or 'YYYY-MM-DD[ HH:MM:SS]')") from None
    date_only = bool(DATE_ONLY_RE.fullmatch(t))
    if dt.tzinfo is None:
        return dt.timestamp(), "local", date_only
    return dt.timestamp(), "aware", date_only


def convert_token(text: str) -> None:
    """打印单个时间戳的转换结果。"""
    ts, kind, _ = parse_when(text)
    if kind in ("epoch", "epoch-ms"):
        suffix = "ms" if kind == "epoch-ms" else "s"
        try:
            local = datetime.fromtimestamp(ts)
            local_s = local.strftime(DEFAULT_FMT)
            iso_s = local.astimezone().isoformat(timespec="seconds")
        except (OverflowError, OSError, ValueError):
            local_s, iso_s = "out-of-local-range", None
        try:
            utc = datetime.fromtimestamp(ts, timezone.utc)
            utc_s = utc.strftime(DEFAULT_FMT)
            if iso_s is None:
                iso_s = utc.isoformat(timespec="seconds")
        except (OverflowError, OSError, ValueError):
            utc_s, iso_s = "out-of-range", ""
        print(f"{text}{suffix}  ->  local: {local_s} | UTC: {utc_s} | ISO: {iso_s}")
    else:
        note = "aware" if kind == "aware" else "local"
        print(f"{text}  ({note})  ->  epoch: {ts:.0f}")


def rel_age(ts: float, now: float) -> str:
    d = (now - ts) / 86400.0
    if d >= 1:
        return f"{d:.1f}d ago"
    if d >= 0:
        return f"{d * 24:.1f}h ago"
    return f"in {-d:.1f}d"


def run_listing(args, after_ts, before_ts) -> None:
    now = time.time()
    attr = FIELD_ATTR[args.field]
    rows = []
    scanned = 0
    for dirpath, _dirs, names in os.walk(args.dir):
        for name in names:
            path = os.path.join(dirpath, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            if not stat_mod.S_ISREG(st.st_mode):
                continue
            scanned += 1
            ts = float(getattr(st, attr))
            if after_ts is not None and ts < after_ts:
                continue
            if before_ts is not None and ts > before_ts:
                continue
            rows.append({"path": path, "ts": ts, "size": st.st_size})
    rows.sort(key=lambda r: r["ts"], reverse=args.desc)
    shown = rows if args.limit is None else rows[: max(args.limit, 0)]

    if args.as_json:
        out = []
        for r in shown:
            try:
                iso_s = datetime.fromtimestamp(r["ts"]).isoformat(timespec="seconds")
            except (OverflowError, OSError, ValueError):
                iso_s = None
            out.append({"path": r["path"], "epoch": r["ts"], "iso_local": iso_s,
                        "size": r["size"]})
        print(json.dumps({"dir": os.path.abspath(args.dir), "field": args.field,
                          "scanned": scanned, "matched": len(rows), "files": out},
                         ensure_ascii=False, indent=2))
        return

    for r in shown:
        try:
            ts_s = datetime.fromtimestamp(r["ts"]).strftime(args.format)
        except (OverflowError, OSError, ValueError):
            ts_s = "out-of-range"
        line = f"{ts_s}  {r['ts']:.0f}  {human_size(r['size']):>9}  {r['path']}"
        if args.relative:
            line += f"  ({rel_age(r['ts'], now)})"
        print(line)
    print(f"-- shown {len(shown)}/{len(rows)} matched (scanned {scanned}) --")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="epoch-converter",
        description="文件时间戳人类可读化; 支持按时间范围筛选文件列表。",
    )
    ap.add_argument("times", nargs="*", metavar="WHEN",
                    help="epoch 秒/毫秒, 或 ISO 日期时间 (本地), 如 1600000000 / 2024-06-01")
    ap.add_argument("--dir", metavar="DIR", help="列出该目录下文件的时间戳")
    ap.add_argument("--field", choices=("mtime", "atime", "ctime"), default="mtime",
                    help="使用哪个时间字段 (Windows 上 ctime 为创建时间)")
    ap.add_argument("--after", metavar="WHEN", help="只列出该时间之后的文件")
    ap.add_argument("--before", metavar="WHEN", help="只列出该时间之前的文件")
    ap.add_argument("--format", metavar="FMT", default=DEFAULT_FMT,
                    help="strftime 格式, 默认 '%%Y-%%m-%%d %%H:%%M:%%S'")
    ap.add_argument("--relative", action="store_true", help="附加距今时长")
    ap.add_argument("--limit", type=int, metavar="N", help="最多输出 N 行")
    ap.add_argument("--desc", action="store_true", help="按时间降序")
    ap.add_argument("--json", dest="as_json", action="store_true", help="以 JSON 输出")
    return ap


def main(argv=None) -> int:
    fix_streams()
    ap = build_parser()
    args = ap.parse_args(argv)

    if args.times:
        for t in args.times:
            try:
                convert_token(t)
            except ValueError as e:
                print(f"error: {e}", file=sys.stderr)
                return 2

    if args.dir:
        if not os.path.isdir(args.dir):
            print(f"error: not a directory: {args.dir}", file=sys.stderr)
            return 2
        after_ts = before_ts = None
        try:
            if args.after:
                after_ts, _, _ = parse_when(args.after)
            if args.before:
                before_ts, _, b_date_only = parse_when(args.before)
                if b_date_only:
                    before_ts += 86399.999  # 纯日期 -> 当天末尾
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        run_listing(args, after_ts, before_ts)

    if not args.times and not args.dir:
        ap.error("nothing to do: give WHEN arguments and/or --dir")
    return 0


if __name__ == "__main__":
    sys.exit(main())
