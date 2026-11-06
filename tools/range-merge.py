#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日期区间合并求交（range-merge）。

对多个“闭区间”日期区间做三种集合运算:
    merge  并集（重叠或首尾相接的区间合并，缺省）
    inter  交集（所有区间的公共部分）
    diff   差集（第 1 个区间依次减去其后的所有区间）

区间写法: 2026-01-01:2026-01-10（冒号 / 逗号 / .. 分隔均可），或单日
2026-01-01。区间作为位置参数依次给出；不带位置参数时从 stdin 逐行
读取（空行与 # 开头的行忽略），便于管道使用。

示例命令:
    python range-merge.py 2026-01-01:2026-01-10 2026-01-08:2026-01-20
    python range-merge.py --op inter 2026-01-01:2026-03-01 2026-02-10:2026-04-01
    python range-merge.py --op diff 2026-01-01:2026-01-31 2026-01-10:2026-01-15
    printf '2026-01-01,2026-01-05\\n2026-01-04..2026-01-09\\n' | python range-merge.py

输出: 每行一个区间 YYYY-MM-DD..YYYY-MM-DD（单日区间起止相同）。
区间起点晚于终点、日期无法解析等参数错误退出码为 2。

仅使用 Python 标准库。
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timedelta

SEP = re.compile(r"\.\.|,|:")


def parse_date(s: str) -> date:
    t = s.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(
        f"无法解析日期: {s!r}（支持 YYYY-MM-DD / YYYY/MM/DD / YYYYMMDD）")


def parse_range(tok: str):
    parts = [p for p in SEP.split(tok.strip()) if p]
    if len(parts) == 1:
        d = parse_date(parts[0])
        return d, d
    if len(parts) == 2:
        s, e = parse_date(parts[0]), parse_date(parts[1])
        if s > e:
            raise argparse.ArgumentTypeError(f"区间起点晚于终点: {tok!r}")
        return s, e
    raise argparse.ArgumentTypeError(
        f"非法区间: {tok!r}（应为 起始:结束，分隔符可用 : , ..，或单个日期）")


def op_merge(segs):
    out = []
    for s, e in sorted(segs):
        if out and s <= out[-1][1] + timedelta(days=1):
            if e > out[-1][1]:
                out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out


def op_inter(segs):
    lo = max(s for s, _ in segs)
    hi = min(e for _, e in segs)
    return [(lo, hi)] if lo <= hi else []


def subtract(segs, b):
    bs, be = b
    out = []
    for s, e in segs:
        if be < s or bs > e:          # 不相交，原样保留
            out.append((s, e))
            continue
        if bs > s:                    # 左侧剩余
            out.append((s, bs - timedelta(days=1)))
        if be < e:                    # 右侧剩余
            out.append((be + timedelta(days=1), e))
    return out


def op_diff(segs):
    res = [segs[0]]
    for b in segs[1:]:
        res = subtract(res, b)
        if not res:
            break
    return res


OPS = {"merge": op_merge, "inter": op_inter, "diff": op_diff}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="range-merge",
        description="对多个日期区间做合并（并集）、求交、差集运算。",
    )
    p.add_argument("ranges", nargs="*",
                   help="区间列表: 2026-01-01:2026-01-10 / 逗号分隔 / 单日；缺省读 stdin")
    p.add_argument("--op", choices=("merge", "inter", "diff"), default="merge",
                   help="运算类型: merge=并集, inter=交集, diff=差集（缺省 merge）")
    return p


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args = build_parser().parse_args(argv)

    tokens = list(args.ranges)
    if not tokens and not sys.stdin.isatty():
        tokens = [line.strip() for line in sys.stdin
                  if line.strip() and not line.strip().startswith("#")]
    if not tokens:
        print("错误: 未提供任何区间（用位置参数或 stdin 给出）", file=sys.stderr)
        return 2

    segs = []
    for t in tokens:
        try:
            segs.append(parse_range(t))
        except argparse.ArgumentTypeError as e:
            print(f"错误: {e}", file=sys.stderr)
            return 2

    for s, e in OPS[args.op](segs):
        print(f"{s.isoformat()}..{e.isoformat()}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
