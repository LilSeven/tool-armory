"""文件清单导出 —— 把目录树信息（路径、大小、修改时间、可选哈希）导出为 CSV 或 JSON。

用法:
    python file-inventory.py <目录> [-o <输出文件>] [--format csv|json] [--hash md5|sha1|sha256]
                             [--glob <模式>] [--rel] [--dirs]

示例:
    python file-inventory.py D:/data -o inventory.csv
    python file-inventory.py D:/data --format json --hash sha256 --rel
    python file-inventory.py ./src --glob "*.py" -o out.csv

说明:
    每行/每项包含: path, size(字节), mtime(本地时间 ISO 格式), 可选 hash（大文件流式读取）。
    -o 省略时写到 stdout；--rel 用相对路径；--dirs 额外包含目录条目。退出码 0 表示成功。
"""

import argparse
import csv
import fnmatch
import datetime
import hashlib
import json
import os
import sys

CHUNK = 1 << 20


def file_hash(path, algo):
    h = hashlib.new(algo)
    try:
        with open(path, "rb") as fh:
            while True:
                block = fh.read(CHUNK)
                if not block:
                    break
                h.update(block)
    except OSError as e:
        print(f"警告: 哈希失败 {path}: {e}", file=sys.stderr)
        return None
    return h.hexdigest()


def build_rows(root, algo=None, pattern=None, rel=False, include_dirs=False):
    rows = []
    base = root if os.path.isdir(root) else os.path.dirname(root) or "."
    for dirpath, dirnames, filenames in os.walk(root):
        entries = list(filenames)
        if include_dirs:
            entries = dirnames + entries
        for name in entries:
            if pattern and not any(fnmatch.fnmatch(name, pat)
                                   for pat in pattern.split(",")):
                continue
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
            except OSError as e:
                print(f"警告: stat 失败 {full}: {e}", file=sys.stderr)
                continue
            shown = os.path.relpath(full, base) if rel else os.path.abspath(full)
            row = {
                "path": shown,
                "size": st.st_size,
                "mtime": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                "is_dir": os.path.isdir(full),
            }
            if algo:
                row["hash"] = None if row["is_dir"] else file_hash(full, algo)
            rows.append(row)
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(description="导出目录树文件清单为 CSV 或 JSON")
    p.add_argument("root", help="目标目录（或单文件）")
    p.add_argument("-o", "--output", default=None, help="输出文件（缺省为 stdout）")
    p.add_argument("--format", choices=["csv", "json"], default="csv")
    p.add_argument("--hash", dest="algo", choices=["md5", "sha1", "sha256"], default=None)
    p.add_argument("--glob", dest="pattern", default=None,
                   help="按文件名通配符过滤，多个用逗号分隔，如 *.txt,*.md")
    p.add_argument("--rel", action="store_true", help="输出相对路径")
    p.add_argument("--dirs", action="store_true", help="包含目录条目")
    args = p.parse_args(argv)

    if not os.path.exists(args.root):
        print(f"错误: 路径不存在: {args.root}", file=sys.stderr)
        return 2

    rows = build_rows(args.root, args.algo, args.pattern, args.rel, args.dirs)

    out = open(args.output, "w", encoding="utf-8-sig", newline="") if args.output else None
    try:
        if args.format == "csv":
            w = csv.DictWriter(out or sys.stdout, fieldnames=["path", "size", "mtime", "is_dir", "hash"])
            w.writeheader()
            for row in rows:
                w.writerow(row)
        else:
            json.dump(rows, out or sys.stdout, ensure_ascii=False, indent=2)
    finally:
        if out:
            out.close()

    dest = args.output or "stdout"
    print(f"共导出 {len(rows)} 条记录 -> {dest}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
