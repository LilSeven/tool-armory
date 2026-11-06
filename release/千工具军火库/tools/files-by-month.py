#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""files-by-month.py —— 按修改年月分组统计文件数量与大小，生成时间轴式占用报表（仅用 Python 标准库）。

按文件最后修改时间（mtime，本地时区）所属“年-月”分组，统计每月文件数与总大小，
按时间先后输出时间轴报表；时间轴上没有文件的月份自动补零行（首末月跨度超过
1200 个月时不再补零）。可按大小或数量画 ASCII 柱状条，并给出各月占总大小的百分比。

示例命令：
    python files-by-month.py D:\\data
    python files-by-month.py D:\\data --bar count          # 柱状条按文件数量为尺度
    python files-by-month.py D:\\data --width 30 --json

退出码：0=成功；2=根目录不存在或不是目录。
"""

import argparse
import json
import os
import sys
import time


def human(n):
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    x = float(n)
    i = 0
    while x >= 1024.0 and i < len(units) - 1:
        x /= 1024.0
        i += 1
    return ("%d %s" % (round(x), units[i])) if i == 0 else ("%.2f %s" % (x, units[i]))


def _reconfigure_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def month_add(ym, k):
    """'2024-08' 偏移 k 个月 -> '2024-09'。"""
    y, m = int(ym[:4]), int(ym[5:7])
    t = y * 12 + (m - 1) + k
    return "%04d-%02d" % (t // 12, t % 12 + 1)


def month_span(a, b):
    """a 到 b 相隔的月数（b>=a）。"""
    return (int(b[:4]) * 12 + int(b[5:7])) - (int(a[:4]) * 12 + int(a[5:7]))


def main():
    _reconfigure_stdio()
    ap = argparse.ArgumentParser(
        description="按修改年月分组统计文件数量与大小，生成时间轴式占用报表。")
    ap.add_argument("root", help="要扫描的根目录")
    ap.add_argument("--bar", choices=("size", "count", "none"), default="size",
                    help="柱状条的度量：size=按大小（默认），count=按数量，none=不画条")
    ap.add_argument("--width", type=int, default=36, help="柱状条最大宽度（默认 36）")
    ap.add_argument("--json", dest="as_json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("错误：根目录不存在或不是目录：%s" % args.root, file=sys.stderr)
        return 2

    agg = {}
    scanned = 0
    total_size = 0
    errors = 0

    def on_error(_e):
        nonlocal errors
        errors += 1

    for dirpath, _dirs, filenames in os.walk(root, onerror=on_error, followlinks=False):
        for name in filenames:
            p = os.path.join(dirpath, name)
            try:
                st = os.lstat(p)
            except OSError:
                errors += 1
                continue
            scanned += 1
            total_size += st.st_size
            month = time.strftime("%Y-%m", time.localtime(st.st_mtime))
            cell = agg.setdefault(month, [0, 0])
            cell[0] += 1
            cell[1] += st.st_size

    if not agg:
        print("未找到任何文件：%s" % root)
        return 0

    months_present = sorted(agg)
    first, last = months_present[0], months_present[-1]
    span = month_span(first, last)
    fill = span + 1 <= 1200
    display = [month_add(first, k) for k in range(span + 1)] if fill else list(months_present)

    if args.as_json:
        rows = []
        for m in display:
            cnt, size = agg.get(m, (0, 0))
            pct = (size / total_size * 100.0) if total_size else 0.0
            rows.append({"month": m, "files": cnt, "size": size, "size_pct": round(pct, 1)})
        out = {"root": root, "scanned": scanned, "total_size": total_size,
               "first_month": first, "last_month": last,
               "months_total": len(display), "empty_months": sum(1 for r in rows if r["files"] == 0),
               "months": rows}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    metric_idx = 1 if args.bar == "size" else 0
    metric_name = "文件大小" if args.bar == "size" else "文件数量"
    maxv = max((agg.get(m, (0, 0))[metric_idx] for m in display), default=0)

    print("按修改年月的时间轴：%s ~ %s，共 %d 个月%s；柱状尺度：%s，宽度 %d"
          % (first, last, len(display), "" if fill else "（跨度过大，未补零月）",
             metric_name, args.width))
    print()

    empty_months = 0
    for m in display:
        cnt, size = agg.get(m, (0, 0))
        if cnt == 0 and size == 0:
            empty_months += 1
        bar = ""
        if args.bar != "none" and maxv > 0:
            v = size if metric_idx == 1 else cnt
            bar_len = int(round(v / maxv * args.width))
            if v > 0 and bar_len == 0:
                bar_len = 1
            bar = "█" * bar_len
        bar = bar.ljust(args.width if args.bar != "none" else 0)
        pct = (size / total_size * 100.0) if total_size else 0.0
        print("%s │%s│ %6d 个 │ %9s │ %5.1f%%" % (m, bar, cnt, human(size), pct))

    print()
    peak_size = max(months_present, key=lambda m: agg[m][1])
    peak_cnt = max(months_present, key=lambda m: agg[m][0])
    print("合计：%d 个文件，%s；无文件月份 %d 个。"
          % (scanned, human(total_size), empty_months))
    print("峰值：大小 %s（%s，%d 个文件）；数量 %s（%d 个文件，%s）。"
          % (peak_size, human(agg[peak_size][1]), agg[peak_size][0],
             peak_cnt, agg[peak_cnt][0], human(agg[peak_cnt][1])))
    if errors:
        print("（警告：%d 个条目无法访问，已跳过）" % errors, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
