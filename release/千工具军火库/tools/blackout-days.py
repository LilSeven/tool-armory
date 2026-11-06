#!/usr/bin/env python3
"""禁用日扣除筛选 —— 从日期区间中扣除禁用日期段，输出剩余可选日期清单。

用法:
    python blackout-days.py <起> <止> [-b 起[:止]]... [--list]

示例命令:
    python blackout-days.py 2026-03-01 2026-03-31 --block 2026-03-05:2026-03-08 --block 2026-03-20
    python blackout-days.py 2026-03-01 2026-03-31 -b 2026-03-05:2026-03-10 --list

规则:
    * 主区间与禁用段均为闭区间（含首尾），日期格式 YYYY-MM-DD。
    * 禁用段写 "起:止"；只写一个日期表示仅禁用当天；可重复出现，
      允许重叠或相邻（内部自动合并）。
    * 输出剩余可选日期的连续区段与统计；--list 额外逐日列出。

仅用 Python 标准库；退出码：0 正常，2 参数错误。
"""

import argparse
import datetime as dt
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def parse_date(text):
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"日期格式应为 YYYY-MM-DD，收到 {text!r}")


def parse_block(text):
    parts = text.split(":")
    if len(parts) == 1:
        d = parse_date(parts[0])
        return d, d
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"禁用段格式应为 起:止，收到 {text!r}")
    s, e = parse_date(parts[0]), parse_date(parts[1])
    if s > e:
        s, e = e, s
    return s, e


def merge_blocks(blocks):
    """合并重叠或相邻（间隔不足 1 天）的闭区间段。"""
    merged = []
    for s, e in sorted(blocks):
        if merged and s <= merged[-1][1] + dt.timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def subtract(start, end, blocks):
    """从 [start, end] 中去掉已排序的 blocks，返回剩余连续区段列表。"""
    remaining = []
    cur = start
    for s, e in blocks:
        if e < cur or s > end:
            continue
        if s > cur:
            remaining.append((cur, s - dt.timedelta(days=1)))
        cur = max(cur, e + dt.timedelta(days=1))
        if cur > end:
            break
    if cur <= end:
        remaining.append((cur, end))
    return remaining


def span_days(s, e):
    return (e - s).days + 1


def fmt_span(s, e):
    return f"{s} ~ {e}（{span_days(s, e)} 天）" if e != s else f"{s}（1 天）"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="从日期区间中扣除禁用日期段，输出剩余可选日期清单。")
    ap.add_argument("start", type=parse_date, help="主区间起始日 YYYY-MM-DD")
    ap.add_argument("end", type=parse_date, help="主区间结束日 YYYY-MM-DD")
    ap.add_argument("-b", "--block", dest="blocks", action="append", default=[],
                    type=parse_block, metavar="起[:止]",
                    help="禁用日期段，可重复；仅写一个日期表示禁用当天")
    ap.add_argument("--list", action="store_true", help="逐日列出剩余可选日期")
    args = ap.parse_args(argv)

    if args.start > args.end:
        ap.error("主区间起始日不能晚于结束日")

    merged = merge_blocks(args.blocks)
    remaining = subtract(args.start, args.end, merged)
    total = span_days(args.start, args.end)
    free = sum(span_days(s, e) for s, e in remaining)
    blocked_in = 0
    for s, e in merged:
        lo, hi = max(s, args.start), min(e, args.end)
        if lo <= hi:
            blocked_in += span_days(lo, hi)

    print(f"主区间：{args.start} ~ {args.end}（{total} 天）")
    if merged:
        print(f"禁用段：合并后 {len(merged)} 段，落在主区间内 {blocked_in} 天：")
        for s, e in merged:
            print(f"  - {fmt_span(s, e)}")
    else:
        print("禁用段：无")
    pct = f"（{free / total * 100:.1f}%）" if total else ""
    print(f"剩余可选：{free} 天{pct}")
    if remaining:
        for s, e in remaining:
            print(f"  {fmt_span(s, e)}")
            if args.list:
                d = s
                while d <= e:
                    print(f"    {d.isoformat()}")
                    d += dt.timedelta(days=1)
    else:
        print("  （主区间内全部日期均被禁用）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
