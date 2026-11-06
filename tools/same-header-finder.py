#!/usr/bin/env python3
"""same-header-finder —— 同表头 CSV 查找器。

读取目录中每个 CSV 文件的首行表头并按内容分组，找出表头相同的文件
（疑似同源/同结构的表格），便于批量合并、去重或校对。
默认忽略字段两端空白与大小写；编码自动尝试 utf-8-sig / gbk / latin-1。

用法:
    python same-header-finder.py <目录> [选项]

选项:
    -r, --recursive      递归扫描子目录
    --ext LIST           视为表格的扩展名，默认 csv（逗号分隔）
    -d, --delimiter SEP  字段分隔符，默认逗号
    --encoding ENC       强制指定编码（默认自动尝试 utf-8-sig/gbk/latin-1）
    --case-sensitive     表头比较区分大小写
    --all                额外列出表头各不相同的文件
    --json               以 JSON 输出

示例:
    python same-header-finder.py D:/data -r
    python same-header-finder.py D:/data --ext csv,tsv -d ";" --all
    python same-header-finder.py D:/data --json

退出码: 0 = 运行成功；2 = 目录不存在。
仅使用 Python 标准库。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

FALLBACK_ENCODINGS = ("utf-8-sig", "gbk", "latin-1")
FIELD_SEP = "\x1f"  # 用不可见单元分隔符拼接字段，避免与内容中的分隔符混淆


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def iter_tables(root: str, exts: set, recursive: bool):
    if recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for name in sorted(filenames):
                if os.path.splitext(name)[1].lower().lstrip(".") in exts:
                    yield os.path.join(dirpath, name)
    else:
        with os.scandir(root) as it:
            entries = sorted(it, key=lambda e: e.name)
        for entry in entries:
            if entry.is_file() and \
                    os.path.splitext(entry.name)[1].lower().lstrip(".") in exts:
                yield entry.path


def read_header(path: str, encodings, delimiter: str):
    """返回 (字段列表, 实际编码)。空文件返回 ([], enc)；无法解码/解析返回 (None, 编码或None)。"""
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, newline="") as handle:
                try:
                    row = next(csv.reader(handle, delimiter=delimiter), None)
                except csv.Error:
                    return None, enc
        except (UnicodeDecodeError, UnicodeError):
            continue
        if row is None:
            return [], enc
        return [field.strip() for field in row], enc
    return None, None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="same-header-finder",
        description="读取各 CSV 文件首行表头，找出表头相同（疑似同源）的文件。",
    )
    parser.add_argument("root", help="要扫描的目录")
    parser.add_argument("-r", "--recursive", action="store_true", help="递归扫描子目录")
    parser.add_argument("--ext", default="csv", metavar="CSV,TSV",
                        help="视为表格文件的扩展名，默认 csv")
    parser.add_argument("-d", "--delimiter", default=",", help="字段分隔符，默认逗号")
    parser.add_argument("--encoding", default="", help="强制文本编码，默认自动尝试")
    parser.add_argument("--case-sensitive", action="store_true", help="表头比较区分大小写")
    parser.add_argument("--all", action="store_true", help="额外列出表头各不相同的文件")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args(argv)

    root = args.root
    if not os.path.isdir(root):
        print(f"错误: 不是目录或不存在: {root}", file=sys.stderr)
        return 2

    exts = {t.strip().lower().lstrip(".") for t in args.ext.split(",") if t.strip()}
    encodings = (args.encoding,) if args.encoding else FALLBACK_ENCODINGS

    records = []    # {"file", "encoding", "fields"}
    unreadable = []
    for path in iter_tables(root, exts, args.recursive):
        try:
            fields, enc = read_header(path, encodings, args.delimiter)
        except OSError as exc:
            unreadable.append({"file": path, "encoding": None, "error": str(exc)})
            continue
        if fields is None:
            unreadable.append({"file": path, "encoding": enc})
        else:
            records.append({"file": path, "encoding": enc, "fields": fields})

    groups: dict = {}
    for rec in records:
        key_fields = rec["fields"] if args.case_sensitive else \
            [f.lower() for f in rec["fields"]]
        groups.setdefault(FIELD_SEP.join(key_fields), []).append(rec)

    multi = sorted((g for g in groups.values() if len(g) >= 2),
                   key=lambda g: FIELD_SEP.join(f.lower() for f in g[0]["fields"]))
    singles = sorted((g[0] for g in groups.values() if len(g) == 1),
                     key=lambda r: r["file"])

    if args.json:
        payload = {
            "root": root,
            "scanned": len(records) + len(unreadable),
            "groups": [
                {
                    "header": g[0]["fields"],
                    "files": [{"file": r["file"], "encoding": r["encoding"]} for r in g],
                }
                for g in multi
            ],
            "singletons": [
                {"file": r["file"], "encoding": r["encoding"], "header": r["fields"]}
                for r in singles
            ] if args.all else [],
            "unreadable": unreadable,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not multi:
        print("未发现表头相同的文件组。")
    else:
        print(f"发现 {len(multi)} 组表头相同的文件（疑似同源）:")
        for idx, g in enumerate(multi, 1):
            header_text = " | ".join(g[0]["fields"]) or "（空表头）"
            print(f"  组 {idx}: [{header_text}]  {len(g)} 个文件")
            for rec in g:
                print(f"    - {rec['file']}  ({rec['encoding']})")
    if singles:
        print(f"表头各不相同的文件 {len(singles)} 个"
              + ("；用 --all 查看明细。" if not args.all else ":"))
        if args.all:
            for rec in singles:
                header_text = " | ".join(rec["fields"]) or "（空文件/无表头）"
                print(f"    - {rec['file']}  ({rec['encoding']})  表头: [{header_text}]")
    if unreadable:
        print(f"无法读取表头的文件 {len(unreadable)} 个:")
        for item in unreadable:
            print(f"    - {item['file']}")
    return 0


if __name__ == "__main__":
    _force_utf8_stdio()
    sys.exit(main())
