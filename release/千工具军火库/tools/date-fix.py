#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多格式日期标准化（date-fix）：尝试一组常见格式模板解析输入日期，统一转换为目标格式输出。

用法:
  python date-fix.py "2025/03/14"                     # 默认输出格式 %Y-%m-%d
  python date-fix.py "14 Mar 2025" -t "%Y年%m月%d日"
  python date-fix.py "2025-03-14 08:30" -t "%Y/%m/%d %H:%M"
  python date-fix.py "14-03-2025" -i "%d-%m-%Y"       # 追加优先尝试的自定义格式（可多次）
示例:
  python date-fix.py "2025/03/14" -t "%Y-%m-%d"    ->  2025-03-14
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

# 常见输入格式模板（顺序即优先级）
COMMON_FORMATS = [
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d",
    "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y", "%m/%d/%Y",
    "%d-%m-%Y", "%m-%d-%Y",
    "%d.%m.%Y", "%m.%d.%Y",
    "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y",
    "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M",
]

USER_FORMATS = [
    "%Y年%m月%d日", "%Y年%m月%d日 %H:%M",
    "%d/%m/%y", "%m/%d/%y",
]


def parse_any(text: str, formats):
    """依次尝试 formats 解析 text；成功返回 (datetime, fmt)，全部失败返回 (None, None)。"""
    text = text.strip()
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt), fmt
        except ValueError:
            continue
    return None, None


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(
        description="多格式日期标准化：尝试一组常见格式模板解析输入日期，统一转换为目标格式输出。")
    ap.add_argument("date", help="输入日期字符串，如 2025/03/14、14 Mar 2025")
    ap.add_argument("-t", "--target", default="%Y-%m-%d",
                    help="目标 strftime 格式（默认 %%Y-%%m-%%d）")
    ap.add_argument("-i", "--input-format", action="append", default=[],
                    help="额外优先尝试的 strptime 格式，可多次给出")
    args = ap.parse_args(argv)

    all_formats = list(args.input_format) + COMMON_FORMATS + USER_FORMATS
    dt, matched = parse_any(args.date, all_formats)
    if dt is None:
        print(f"错误：无法解析日期 {args.date!r}（尝试了 {len(all_formats)} 种格式）",
              file=sys.stderr)
        return 1
    try:
        out = dt.strftime(args.target)
    except (ValueError, TypeError) as exc:
        print(f"错误：目标格式 {args.target!r} 无效：{exc}", file=sys.stderr)
        return 2
    print(f"{out}\t# 匹配格式: {matched}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
