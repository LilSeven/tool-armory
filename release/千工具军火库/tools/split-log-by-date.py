#!/usr/bin/env python3
"""日志按日期拆分 (split-log-by-date)

识别日志行前缀中的时间戳，把混合日志按日期拆成按天命名的日志文件。

支持的时间戳格式（行首附近）：
  2024-01-02 03:04:05          (ISO 常见格式)
  2024-01-02T03:04:05          (ISO 8601)
  [2024/01/02 03:04:05]        (方括号 + 斜杠)
  Jan 02 03:04:05              (syslog 英文月份，年份取 --year，默认当前年)

用法:
  python split-log-by-date.py mixed.log -o outdir --prefix app
  python split-log-by-date.py mixed.log -o outdir --prefix app --year 2023

无法识别时间戳的行会追加到上一个可识别日期的文件；文件开头的
无法归属行归入 --orphan 指定的日期文件（默认 0000-00-00）。

示例命令:
  python split-log-by-date.py mixed.log -o ./days --prefix app
"""

import argparse
import os
import re
import sys

MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}

# 2024-01-02 或 2024/01/02，后面可选时间
RE_ISO = re.compile(
    r"(\d{4})[-/](\d{2})[-/](\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2})?)?")
# syslog 风格: Jan 02 03:04:05
RE_SYSLOG = re.compile(
    r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})\b")


def extract_date(line, year):
    """从一行日志前缀中提取日期，返回 'YYYY-MM-DD' 或 None。"""
    m = RE_ISO.search(line[:80])
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            import datetime
            datetime.date(y, mo, d)
        except ValueError:
            return None
        return "%04d-%02d-%02d" % (y, mo, d)
    m = RE_SYSLOG.search(line[:80])
    if m:
        mo = MONTHS[m.group(1)]
        d = int(m.group(2))
        try:
            import datetime
            datetime.date(year, mo, d)
        except ValueError:
            return None
        return "%04d-%02d-%02d" % (year, mo, d)
    return None


def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip() or "unknown"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="把混合日志按行前缀时间戳的日期拆分成按天命名的文件")
    ap.add_argument("input", help="输入日志文件")
    ap.add_argument("-o", "--outdir", default=".",
                    help="输出目录（默认当前目录）")
    ap.add_argument("--prefix", default="log", help="输出文件名前缀")
    ap.add_argument("--ext", default=".log", help="输出文件扩展名（默认 .log）")
    ap.add_argument("--year", type=int, default=None,
                    help="syslog 风格时间戳使用的年份（默认当前年）")
    ap.add_argument("--orphan", default="0000-00-00",
                    help="开头无法归属日期的行的目标日期（默认 0000-00-00）")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.input):
        print("错误: 输入文件不存在: %s" % args.input, file=sys.stderr)
        return 2

    if args.year is None:
        import datetime
        args.year = datetime.date.today().year

    os.makedirs(args.outdir, exist_ok=True)

    counts = {}
    current = None
    handles = {}

    def write(date_key, line):
        h = handles.get(date_key)
        if h is None:
            fname = sanitize_filename(
                "%s-%s%s" % (args.prefix, date_key, args.ext))
            h = open(os.path.join(args.outdir, fname), "w",
                     encoding="utf-8", newline="")
            handles[date_key] = h
        h.write(line)
        counts[date_key] = counts.get(date_key, 0) + 1

    with open(args.input, "r", encoding="utf-8", errors="replace") as fin:
        for line in fin:
            d = extract_date(line, args.year)
            if d is not None:
                current = d
            if current is None:
                current = args.orphan
            write(current, line)

    for h in handles.values():
        h.close()

    for k in sorted(counts):
        print("%s: %d 行" % (k, counts[k]))
    print("共输出 %d 个文件到 %s" % (len(counts), args.outdir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
