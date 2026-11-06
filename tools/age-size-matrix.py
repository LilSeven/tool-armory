#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件年龄×大小矩阵（age-size-matrix）

用途：
    按"最后修改时间距今的天数"与"文件大小"两个维度对目录树做二维分桶，
    统计每个格子的文件数量与字节总量，并单独标出"又老又大"的格子
    （>= 最大年龄分界 且 > 最大大小分界），帮助定位长期没人动、
    却占着大量空间的陈年文件。

默认分桶（均可用参数改为升序分界点）：
    年龄：<30天 | 30~90天 | 90~365天 | >=365天   （依据 mtime）
    大小：<=1MB | 1~10MB | 10~100MB | >100MB

示例命令：
    python age-size-matrix.py D:/data
    python age-size-matrix.py D:/data --age-days 30,90,365 --size-buckets 1MB,10MB,100MB
    python age-size-matrix.py C:/Users/me/Documents --json

退出码：0 正常完成；1 参数或路径错误。
"""

import argparse
import json
import os
import re
import stat
import sys
import time
import unicodedata

_SIZE_UNITS = {"": 1, "B": 1, "K": 1024, "KB": 1024, "M": 1024 ** 2, "MB": 1024 ** 2,
               "G": 1024 ** 3, "GB": 1024 ** 3, "T": 1024 ** 4, "TB": 1024 ** 4}


def parse_size(text):
    """'4096' / '1MB' / '512k' -> 字节数；无法解析时抛 ValueError。"""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([BKMGT]?)B?", text.strip(), re.IGNORECASE)
    if not m:
        raise ValueError(f"无法解析大小：{text!r}")
    return int(float(m.group(1)) * _SIZE_UNITS[m.group(2).upper()])


def parse_list(text, item_parser, name):
    raw = [x.strip() for x in text.split(",") if x.strip()]
    try:
        values = [item_parser(x) for x in raw]
    except ValueError as exc:
        raise ValueError(f"--{name} 解析失败：{exc}") from None
    if len(values) < 1:
        raise ValueError(f"--{name} 至少需要 1 个分界点")
    if any(v <= 0 for v in values):
        raise ValueError(f"--{name} 的分界点必须为正数")
    if any(b <= a for a, b in zip(values, values[1:])):
        raise ValueError(f"--{name} 的分界点必须严格升序")
    return values


def human(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024 or unit == "PB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.2f} {unit}"
        n /= 1024.0


def disp_width(s):
    """估算终端显示宽度：东亚全角字符按 2 列计。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def pad(s, width):
    return s + " " * max(0, width - disp_width(s))


def age_labels(boundaries):
    labels, prev = [], None
    for b in boundaries:
        labels.append(f"<{b}天" if prev is None else f"{prev}~{b}天")
        prev = b
    labels.append(f">={prev}天")
    return labels


def size_labels(boundaries):
    labels, prev = [], None
    for b in boundaries:
        labels.append(f"<={human(b)}" if prev is None else f"{human(prev)}~{human(b)}")
        prev = b
    labels.append(f">{human(prev)}")
    return labels


def collect(root, age_days, size_bounds):
    """扫描目录树，返回 (计数矩阵, 字节矩阵, 文件总数, 跳过数)。"""
    now = time.time()
    na, ns = len(age_days) + 1, len(size_bounds) + 1
    counts = [[0] * ns for _ in range(na)]
    totals = [[0] * ns for _ in range(na)]
    nfiles = skipped = 0

    def walk_error(_err):
        nonlocal skipped
        skipped += 1

    for dirpath, dirnames, filenames in os.walk(root, onerror=walk_error):
        dirnames.sort()
        for name in sorted(filenames):
            p = os.path.join(dirpath, name)
            try:
                st = os.lstat(p)
            except OSError:
                skipped += 1
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            age = max(0.0, (now - st.st_mtime) / 86400.0)
            ai = na - 1
            for i, b in enumerate(age_days):
                if age < b:
                    ai = i
                    break
            si = ns - 1
            for i, b in enumerate(size_bounds):
                if st.st_size <= b:
                    si = i
                    break
            counts[ai][si] += 1
            totals[ai][si] += st.st_size
            nfiles += 1
    return counts, totals, nfiles, skipped


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(
        prog="age-size-matrix",
        description="按文件年龄与大小二维分组统计数量与总量，定位又老又大的文件。")
    parser.add_argument("path", help="要扫描的目录")
    parser.add_argument("--age-days", default="30,90,365", metavar="D1,D2,...",
                        help="年龄分界点（天，升序逗号分隔，默认 30,90,365）")
    parser.add_argument("--size-buckets", default="1MB,10MB,100MB", metavar="S1,S2,...",
                        help="大小分界点（升序逗号分隔，支持 KB/MB 等后缀，默认 1MB,10MB,100MB）")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.path):
        print(f"错误：{args.path} 不是有效目录", file=sys.stderr)
        return 1
    try:
        age_days = parse_list(args.age_days, int, "age-days")
        size_bounds = parse_list(args.size_buckets, parse_size, "size-buckets")
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    counts, totals, nfiles, skipped = collect(args.path, age_days, size_bounds)
    a_lbl = age_labels(age_days)
    s_lbl = size_labels(size_bounds)
    grand_c = sum(sum(r) for r in counts)
    grand_t = sum(sum(r) for r in totals)

    if args.json:
        rows = []
        for i, la in enumerate(a_lbl):
            rows.append({
                "age": la,
                "cells": [{"size": ls, "count": counts[i][j], "bytes": totals[i][j]}
                          for j, ls in enumerate(s_lbl)],
                "total_count": sum(counts[i]),
                "total_bytes": sum(totals[i]),
            })
        print(json.dumps({
            "root": os.path.abspath(args.path),
            "age_days": age_days, "size_bounds": size_bounds,
            "files": nfiles, "skipped": skipped,
            "matrix": rows,
            "old_and_big": {"age": a_lbl[-1], "size": s_lbl[-1],
                            "count": counts[-1][-1], "bytes": totals[-1][-1]},
        }, ensure_ascii=False, indent=2))
        return 0

    header = ["年龄\\大小"] + s_lbl + ["合计"]
    table = []
    for i, la in enumerate(a_lbl):
        cells = [f"{counts[i][j]}个/{human(totals[i][j])}" for j in range(len(s_lbl))]
        cells.append(f"{sum(counts[i])}个/{human(sum(totals[i]))}")
        table.append([la] + cells)
    total_row = ["合计"]
    for j in range(len(s_lbl)):
        c = sum(counts[i][j] for i in range(len(a_lbl)))
        t = sum(totals[i][j] for i in range(len(a_lbl)))
        total_row.append(f"{c}个/{human(t)}")
    total_row.append(f"{grand_c}个/{human(grand_t)}")
    table.append(total_row)

    widths = [max(disp_width(r[c]) for r in [header] + table) for c in range(len(header))]
    print("文件数/字节总量 矩阵（行=年龄，列=大小）：")
    print("  ".join(pad(c, widths[i]) for i, c in enumerate(header)))
    for row in table:
        print("  ".join(pad(c, widths[i]) for i, c in enumerate(row)))
    print(f"\n共 {nfiles} 个文件，{human(grand_t)}；跳过 {skipped} 处不可读。")
    print(f"★ 又老又大（{a_lbl[-1]} 且 {s_lbl[-1]}）：{counts[-1][-1]} 个，"
          f"共 {human(totals[-1][-1])}。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
