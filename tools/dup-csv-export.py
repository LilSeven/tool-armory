#!/usr/bin/env python3
"""重复清单导出器（dup-csv-export）

用途:
    读取"重复文件分组结果"清单（每组一行一个路径，组与组之间用空行
    分隔，与 fdupes 的输出格式一致），补上每组建议保留项、文件大小、
    修改时间与是否存在标记，导出为 CSV 或 JSON，并留出空的 selected
    列，方便在 Excel / WPS 等表格软件中勾选审阅后批量处理。

示例命令:
    python dup-csv-export.py dupes.txt -o dupes.csv
    python dup-csv-export.py dupes.txt --format json -o dupes.json
    cat dupes.txt | python dup-csv-export.py -

说明:
    - keep 列 = 建议保留项（取每组第一行）；selected 列留空待人工勾选。
    - 清单中已不存在的文件照常导出: size_bytes/mtime 为空、exists=N。
    - 输入清单按 UTF-8（含 BOM）读取；CSV 输出为 UTF-8 带 BOM，
      Excel 可直接打开且中文不乱码。

退出码:
    0 = 成功（含空清单）
    1 = 输入文件读取失败
    2 = 参数错误
"""

import argparse
import csv
import datetime
import json
import os
import sys

CSV_FIELDS = ["group_id", "keep", "path", "size_bytes", "mtime", "exists", "selected"]


def _safe_stdout():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass


def parse_groups(text):
    """按空行分隔分组；返回 [[path, ...], ...]"""
    groups, current = [], []
    for line in text.splitlines():
        s = line.strip()
        if s:
            current.append(s)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def stat_file(path):
    """返回 (size_bytes 或 None, mtime ISO 字符串 或 None)"""
    try:
        st = os.stat(path)
    except OSError:
        return None, None
    mtime = datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
    return st.st_size, mtime


def build_rows(groups):
    rows = []
    for gi, group in enumerate(groups, 1):
        keep_path = group[0]
        for path in group:
            size, mtime = stat_file(path)
            rows.append({
                "group_id": gi,
                "keep": "Y" if path == keep_path else "",
                "path": path,
                "size_bytes": size,
                "mtime": mtime,
                "exists": "Y" if mtime is not None else "N",
                "selected": "",
            })
    return rows


def write_csv(rows, out):
    if out == "-":
        writer = csv.DictWriter(sys.stdout, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    else:
        with open(out, "w", newline="", encoding="utf-8-sig") as fp:
            writer = csv.DictWriter(fp, fieldnames=CSV_FIELDS, lineterminator="\r\n")
            writer.writeheader()
            writer.writerows(rows)


def rows_to_json(rows):
    by_group = {}
    for r in rows:
        by_group.setdefault(r["group_id"], []).append(r)
    groups = []
    for gid in sorted(by_group):
        members = by_group[gid]
        groups.append({
            "id": gid,
            "keep": next(r["path"] for r in members if r["keep"] == "Y"),
            "files": [{"path": r["path"], "size_bytes": r["size_bytes"],
                       "mtime": r["mtime"], "exists": r["exists"],
                       "selected": r["selected"]} for r in members],
        })
    return {"total_groups": len(groups),
            "total_files": sum(len(g["files"]) for g in groups),
            "groups": groups}


def main(argv=None):
    _safe_stdout()
    parser = argparse.ArgumentParser(
        description="把重复文件分组结果导出为 CSV/JSON，便于在表格软件中勾选审阅处理。")
    parser.add_argument("input", help="重复分组清单文件（每行一个路径，空行分组）；'-' 表示从 stdin 读取")
    parser.add_argument("--format", choices=("csv", "json"), default="csv",
                        help="导出格式（默认 csv）")
    parser.add_argument("-o", "--out", default="-",
                        help="输出文件路径；缺省打印到屏幕")
    args = parser.parse_args(argv)

    try:
        if args.input == "-":
            text = sys.stdin.read()
        else:
            with open(args.input, "r", encoding="utf-8-sig", errors="replace") as fp:
                text = fp.read()
    except OSError as exc:
        print("错误: 无法读取输入文件: %s" % exc, file=sys.stderr)
        return 1

    groups = parse_groups(text)
    if not groups:
        print("警告: 输入中未发现任何重复组（应为: 每行一个路径，空行分组）。", file=sys.stderr)
    rows = build_rows(groups)

    if args.format == "csv":
        write_csv(rows, args.out)
    else:
        payload = rows_to_json(rows)
        if args.out == "-":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            with open(args.out, "w", encoding="utf-8") as fp:
                json.dump(payload, fp, ensure_ascii=False, indent=2)
                fp.write("\n")

    dest = "屏幕" if args.out == "-" else args.out
    print("已导出 %d 组 / %d 个文件 -> %s" % (len(groups), len(rows), dest), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
