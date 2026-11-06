#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日志透视报表 —— 按两个维度(如 级别×小时)交叉统计日志条数, 输出透视表。

用途:
    逐行读取日志, 提取"级别"与"时间"两类维度, 任选行列交叉统计条数,
    输出带行列合计的透视表。常见级别(TRACE/DEBUG/INFO/NOTICE/WARN/ERROR/
    CRITICAL/FATAL, 大小写不敏感)与形如 "2026-11-03 09:15:00" 的时间戳均可
    识别; 识别不出的行归入 UNKNOWN / ? 桶, 不会被丢弃。

示例:
    python log-pivot-report.py app.log                          # 行=级别, 列=小时
    python log-pivot-report.py app.log --rows hour --cols level # 行列互换
    python log-pivot-report.py app.log --rows date --cols level # 日期×级别
    tail -n 1000 app.log | python log-pivot-report.py -         # 从 stdin 读取
    python log-pivot-report.py app.log --encoding gbk           # 指定输入编码

退出码: 0 成功; 2 参数或文件读取错误。
"""

import argparse
import re
import sys
import unicodedata
from collections import Counter

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
HOUR_RE = re.compile(r"\d{4}-\d{2}-\d{2}[ T](?P<hour>\d{2}):\d{2}")
LEVEL_RE = re.compile(
    r"\b(CRITICAL|WARNING|TRACE|NOTICE|FATAL|DEBUG|ERROR|CRIT|WARN|INFO|ERR)\b",
    re.IGNORECASE,
)
LEVEL_NORM = {"WARNING": "WARN", "CRITICAL": "CRIT", "ERR": "ERROR"}
LEVEL_ORDER = ["TRACE", "DEBUG", "INFO", "NOTICE", "WARN", "ERROR", "CRIT", "FATAL"]
DIM_CHOICES = ("level", "hour", "date")
DIM_LABEL = {"level": "级别", "hour": "小时", "date": "日期"}


def _setup_stdio():
    """Windows 下把标准输出/错误切到 UTF-8, 避免中文在管道/重定向中乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def extract_dim(kind, line):
    """从一行日志中提取指定维度(kind)的取值。"""
    if kind == "level":
        m = LEVEL_RE.search(line)
        if not m:
            return "UNKNOWN"
        name = m.group(1).upper()
        return LEVEL_NORM.get(name, name)
    if kind == "hour":
        m = HOUR_RE.search(line)
        return m.group("hour") if m else "?"
    m = DATE_RE.search(line)
    return m.group(0) if m else "?"


def dim_sort_key(kind, value):
    """维度取值排序: 级别按严重度, 时间按字典序; UNKNOWN/? 排最后。"""
    if value in ("?", "UNKNOWN"):
        return (1, "", 0)
    if kind == "level":
        try:
            return (0, value, LEVEL_ORDER.index(value))
        except ValueError:
            return (0, value, 0)
    return (0, value, 0)


def disp_width(text):
    """终端显示宽度: 东亚全角/宽字符按 2 列计。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
               for ch in text)


def pad_left_align(text, width):
    return text + " " * (width - disp_width(text))


def render_pivot(row_kind, col_kind, counts, source):
    total = sum(counts.values())
    row_vals = sorted({r for r, _ in counts},
                      key=lambda v: dim_sort_key(row_kind, v))
    col_vals = sorted({c for _, c in counts},
                      key=lambda v: dim_sort_key(col_kind, v))

    lines = ["透视表: 行={} × 列={} | 共 {} 条日志 | 来源: {}".format(
        DIM_LABEL[row_kind], DIM_LABEL[col_kind], total, source)]
    if not row_vals:
        lines.append("(未解析到任何日志行)")
        return "\n".join(lines)

    headers = [DIM_LABEL[row_kind]] + col_vals + ["合计"]
    body = []
    for rv in row_vals:
        cells = [counts.get((rv, cv), 0) for cv in col_vals]
        body.append([rv] + [str(n) for n in cells] + [str(sum(cells))])
    col_totals = [sum(counts.get((rv, cv), 0) for rv in row_vals)
                  for cv in col_vals]
    footer = ["合计"] + [str(n) for n in col_totals] + [str(sum(col_totals))]

    widths = [max(disp_width(headers[i]),
                  max((disp_width(r[i]) for r in body), default=0),
                  disp_width(footer[i]))
              for i in range(len(headers))]

    def fmt_row(cells):
        parts = []
        for i, cell in enumerate(cells):
            parts.append(pad_left_align(cell, widths[i]) if i == 0
                         else cell.rjust(widths[i]))
        return "  ".join(parts)

    lines.append(fmt_row(headers))
    lines.append("  ".join("-" * w for w in widths))
    lines.extend(fmt_row(r) for r in body)
    lines.append("  ".join("-" * w for w in widths))
    lines.append(fmt_row(footer))
    return "\n".join(lines)


def iter_lines(source, encoding):
    if source == "-":
        if hasattr(sys.stdin, "reconfigure"):
            try:
                sys.stdin.reconfigure(encoding=encoding, errors="replace")
            except (OSError, ValueError):
                pass
        yield from sys.stdin
    else:
        with open(source, "r", encoding=encoding, errors="replace") as fh:
            yield from fh


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="log-pivot-report",
        description="按两个维度(如 级别×小时)交叉统计日志条数, 输出透视表。")
    parser.add_argument("logfile", help="日志文件路径; 传 '-' 从 stdin 读取")
    parser.add_argument("--rows", choices=DIM_CHOICES, default="level",
                        help="行维度 (默认 level)")
    parser.add_argument("--cols", choices=DIM_CHOICES, default="hour",
                        help="列维度 (默认 hour)")
    parser.add_argument("--encoding", default="utf-8",
                        help="输入文件编码 (默认 utf-8)")
    args = parser.parse_args(argv)

    counts = Counter()
    try:
        for line in iter_lines(args.logfile, args.encoding):
            if not line.strip():
                continue
            key = (extract_dim(args.rows, line), extract_dim(args.cols, line))
            counts[key] += 1
    except OSError as exc:
        print("错误: 无法读取 {}: {}".format(args.logfile, exc), file=sys.stderr)
        return 2

    source = "stdin" if args.logfile == "-" else args.logfile
    print(render_pivot(args.rows, args.cols, counts, source))
    return 0


if __name__ == "__main__":
    _setup_stdio()
    sys.exit(main())
