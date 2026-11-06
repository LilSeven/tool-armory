#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strftime 速查试算（format-cheatsheet）：列出 strftime/strptime 全部格式码并用当前时间实例试算展示。

用法:
  python format-cheatsheet.py            # 用本地当前时间试算全部格式码
  python format-cheatsheet.py --utc      # 用 UTC 当前时间（%z/%Z 会有实际值）
  python format-cheatsheet.py --at "2026-03-14 15:04:05"
示例:
  python format-cheatsheet.py --utc    ->  每行一条：格式码  说明  用当前时间算出的结果
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

DIRECTIVES = [
    ("%Y", "四位年份 (2026)"),
    ("%y", "两位年份 (00-99)"),
    ("%C", "世纪 (00-99)"),
    ("%m", "月份 (01-12)"),
    ("%d", "日 (01-31)"),
    ("%e", "日，空格补位 ( 1-31)"),
    ("%H", "小时 24 进制 (00-23)"),
    ("%I", "小时 12 进制 (01-12)"),
    ("%p", "AM/PM（随本地语言）"),
    ("%M", "分钟 (00-59)"),
    ("%S", "秒 (00-59)"),
    ("%f", "微秒，6 位补零"),
    ("%z", "UTC 偏移 +HHMM（naive 时间为空）"),
    ("%Z", "时区名（naive 时间为空）"),
    ("%j", "年内第几天 (001-366)"),
    ("%U", "年内第几周，周日起算 (00-53)"),
    ("%W", "年内第几周，周一起算 (00-53)"),
    ("%a", "星期缩写（随本地语言）"),
    ("%A", "星期全名（随本地语言）"),
    ("%b", "月份缩写（随本地语言）"),
    ("%B", "月份全名（随本地语言）"),
    ("%c", "本地化完整日期时间"),
    ("%x", "本地化日期"),
    ("%X", "本地化时间"),
    ("%G", "ISO 8601 年份"),
    ("%u", "ISO 星期 (1=周一 … 7=周日)"),
    ("%V", "ISO 8601 周号 (01-53)"),
    ("%%", "百分号本身"),
    ("%n", "换行符"),
    ("%t", "制表符"),
]

# strptime 试算样例：样例字符串与其格式码
SAMPLES = [
    ("2026-11-02 15:04:05", "%Y-%m-%d %H:%M:%S"),
    ("02/11/2026", "%d/%m/%Y"),
    ("Nov 02, 2026", "%b %d, %Y"),
    ("2026-306", "%Y-%j"),
    ("2026-W45-1", "%G-W%V-%u"),
    ("03:04 PM", "%I:%M %p"),
]


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(
        description="strftime 速查试算：列出全部格式码并用当前时间实例试算展示。")
    ap.add_argument("--utc", action="store_true", help="使用 UTC 当前时间试算")
    ap.add_argument("--at", metavar="TIME",
                    help="指定试算时刻，格式 YYYY-MM-DD[ HH:MM[:SS]]")
    args = ap.parse_args(argv)

    if args.at:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                now = datetime.strptime(args.at.strip(), fmt)
                break
            except ValueError:
                continue
        else:
            print(f"错误：--at 需为 YYYY-MM-DD[ HH:MM[:SS]] 格式，收到 {args.at!r}",
                  file=sys.stderr)
            return 2
    elif args.utc:
        now = datetime.now(timezone.utc)
    else:
        now = datetime.now()

    label = now.strftime("%Y-%m-%d %H:%M:%S %z").strip()
    print(f"试算基准时间: {label or now}（%a/%p/%b 等输出随系统本地语言而异）")
    print()
    print("== strftime 试算 ==")
    print(f"{'格式码':<6} {'说明':<32} 结果")
    print("-" * 72)
    for code, desc in DIRECTIVES:
        try:
            val = now.strftime(code)
        except Exception as exc:                    # 平台不支持某格式码
            val = f"<此平台不支持: {exc}>"
        print(f"{code:<6} {desc:<32} {val!r}")
    print()
    print("== strptime 试算 ==")
    for text, fmt in SAMPLES:
        try:
            parsed = datetime.strptime(text, fmt)
            print(f"  {text!r:<24} --{fmt:<18}-->  {parsed}")
        except ValueError as exc:
            print(f"  {text!r:<24} --{fmt:<18}-->  <解析失败: {exc}>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
