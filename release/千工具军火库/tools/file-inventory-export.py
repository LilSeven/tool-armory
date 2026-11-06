#!/usr/bin/env python3
"""文件清单导出器（file-inventory-export）。

把目录树清单（路径、类型、大小、时间、可选哈希）导出为 CSV 或
JSON。默认输出到标准输出，用 -o 保存为文件（UTF-8 编码）。
时间字段为 ISO 8601 本地时间；Windows 上 st_ctime 为创建时间，
POSIX 上为元数据变更时间。哈希仅对普通文件计算，符号链接不跟随。

示例命令：
    python file-inventory-export.py ./data                          # CSV 到 stdout
    python file-inventory-export.py ./data -o out.csv               # CSV 保存为文件
    python file-inventory-export.py ./data --format json --hash sha256 -o out.json
    python file-inventory-export.py ./data --files-only --absolute  # 只列文件、绝对路径
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import stat as stat_mod
import sys

CHUNK = 1 << 20
CSV_HEADER = ["path", "type", "size_bytes", "mtime", "ctime", "atime", "hash", "error"]


def iso(ts: float) -> str:
    """时间戳 -> ISO 8601 本地时间字符串，失败返回空串。"""
    try:
        return dt.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return ""


def file_hash(path: str, algo: str) -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _entry(full: str, top: str, args, errors: list, is_dir: bool = False) -> dict:
    rel = os.path.relpath(full, top)
    if args.absolute:
        rel = os.path.abspath(full)
    try:
        st = os.lstat(full)
    except OSError as exc:
        errors[0] += 1
        return {"path": rel, "type": "error", "size_bytes": None,
                "mtime": "", "ctime": "", "atime": "", "hash": None,
                "error": str(exc)}

    if is_dir:
        etype = "directory"
        size = None
    elif stat_mod.S_ISLNK(st.st_mode):
        etype = "symlink"
        size = st.st_size
    else:
        etype = "file"
        size = st.st_size

    digest = None
    err = None
    if args.hash and etype == "file":
        try:
            digest = file_hash(full, args.hash)
        except OSError as exc:
            errors[0] += 1
            return {"path": rel, "type": etype, "size_bytes": size,
                    "mtime": iso(st.st_mtime), "ctime": iso(st.st_ctime),
                    "atime": iso(st.st_atime), "hash": None,
                    "error": "hash: %s" % exc}
    return {"path": rel, "type": etype, "size_bytes": size,
            "mtime": iso(st.st_mtime), "ctime": iso(st.st_ctime),
            "atime": iso(st.st_atime), "hash": digest, "error": err}


def scan(top: str, args, errors: list) -> list:
    entries = []
    for root, dirs, files in os.walk(top, topdown=True, followlinks=False):
        dirs.sort()
        files.sort()
        # 记录目录本身（含顶层 "."）；符号链接目录不会作为 root 访问，单独补记
        entries.append(_entry(root, top, args, errors, is_dir=True))
        for name in dirs:
            full = os.path.join(root, name)
            if os.path.islink(full):
                entries.append(_entry(full, top, args, errors))
        for name in files:
            entries.append(_entry(os.path.join(root, name), top, args, errors))
    if args.files_only:
        entries = [e for e in entries if e["type"] != "directory"]
    return entries


def to_csv(entries: list) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for e in entries:
        writer.writerow([
            e["path"], e["type"],
            "" if e["size_bytes"] is None else e["size_bytes"],
            e["mtime"], e["ctime"], e["atime"],
            e["hash"] or "", e["error"] or "",
        ])
    return buf.getvalue()


def to_json(entries: list, top: str, args) -> str:
    return json.dumps({
        "top": os.path.abspath(top),
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "hash_algo": args.hash,
        "count": len(entries),
        "entries": entries,
    }, ensure_ascii=False, indent=2)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="把目录树清单（路径、大小、时间、可选哈希）导出为 CSV 或 JSON")
    parser.add_argument("top", help="要扫描的目录")
    parser.add_argument("-o", "--output", help="输出文件路径（默认标准输出）")
    parser.add_argument("--format", choices=("csv", "json"), default="csv",
                        help="输出格式（默认 csv）")
    parser.add_argument("--hash", choices=("md5", "sha1", "sha256"),
                        help="对普通文件计算指定哈希")
    parser.add_argument("--files-only", action="store_true",
                        help="不含目录行，只列文件与符号链接")
    parser.add_argument("--absolute", action="store_true", help="使用绝对路径")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not os.path.isdir(args.top):
        print("错误：目录不存在：%s" % args.top, file=sys.stderr)
        return 2

    errors = [0]
    entries = scan(args.top, args, errors)
    if args.format == "csv":
        text = to_csv(entries)
    else:
        text = to_json(entries, args.top, args)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
            if args.format == "json":
                fh.write("\n")
        print("已导出 %d 条记录（%d 个错误）-> %s"
              % (len(entries), errors[0], args.output), file=sys.stderr)
    else:
        sys.stdout.write(text)
        if args.format == "json":
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
