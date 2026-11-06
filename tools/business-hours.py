#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""营业时长计算 —— 按自定义每日营业时段（可多段，如含午休；支持跨午夜
时段），并可配置周末与节假日，计算两个时刻之间的有效营业小时数，支持跨天。

用法:
    python business-hours.py "2026-11-02 09:00" "2026-11-04 18:00" --detail
    python business-hours.py "2026-11-02 09:00" "2026-11-04 18:00" --hours "09:00-12:00,13:00-18:00"
    python business-hours.py "2026-11-06 22:00" "2026-11-07 02:00" --hours "10:00-02:00" --weekend none

参数:
    START END        时刻: YYYY-MM-DD[ HH:MM[:SS]]（可空格或 T 分隔；缺省 00:00）
    --hours          每日营业时段，逗号分隔多段，段内 A-B；B<=A 视为跨午夜
                     （如 10:00-02:00），结束写 00:00 表示到午夜（默认 09:00-18:00）
    --weekend        每周休息日: mon..sun / 一..日 / 周X / 1-7（ISO，1=周一），
                     逗号分隔；none 表示无周休（默认 sat,sun）
    --closed         额外歇业日 YYYY-MM-DD 或 A..B 区间，可重复或逗号分隔
    --detail         按日打印明细（跨午夜时段归属其起始日，次日清晨部分
                     计入实际发生的自然日）

示例输出:
    $ python business-hours.py "2026-11-02 09:00" "2026-11-04 18:00" --hours "09:00-12:00,13:00-18:00"
    统计区间 : 2026-11-02 09:00 ~ 2026-11-04 18:00
    营业时段 : 09:00-12:00 / 13:00-18:00
    周休     : 周六、周日 ；节假日: 无
    有效营业 : 24.00 小时 (1440 分钟)

退出码: 0 成功(含 0 小时); 2 参数、时刻或时段格式错误（含 END 早于 START）。
仅用 Python 标准库，单文件。
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time, timedelta

WD_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
WD_NUM = {"mon": 1, "tue": 2, "tues": 2, "wed": 3, "thu": 4, "thur": 4, "thurs": 4,
          "fri": 5, "sat": 6, "sun": 7}


def _setup_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def parse_dt(text: str) -> datetime:
    """解析 YYYY-MM-DD[ HH:MM[:SS]]（分隔符可为空格或 T），失败抛 ValueError。"""
    t = text.strip().replace("T", " ").replace("t", " ")
    pieces = t.split()
    try:
        if len(pieces) == 1:
            return datetime.combine(date.fromisoformat(pieces[0]), time(0, 0))
        if len(pieces) == 2:
            tm = pieces[1]
            fmt = "%H:%M:%S" if tm.count(":") == 2 else "%H:%M"
            return datetime.combine(date.fromisoformat(pieces[0]),
                                    datetime.strptime(tm, fmt).time())
    except ValueError:
        pass
    raise ValueError(f"无法解析时刻 {text!r}，应为 YYYY-MM-DD[ HH:MM[:SS]]")


def parse_hours(spec: str):
    """解析逗号分隔的时段列表，返回 [(time,time),...]；B<=A 表示跨午夜。"""
    segs = []
    for piece in spec.split(","):
        piece = piece.strip()
        if not piece:
            continue
        a, sep, b = piece.partition("-")
        if not sep:
            raise ValueError(f"时段缺少“-”: {piece!r}")
        try:
            t1 = datetime.strptime(a.strip(), "%H:%M").time()
            t2 = datetime.strptime(b.strip(), "%H:%M").time()
        except ValueError:
            raise ValueError(f"时段格式应为 HH:MM-HH:MM: {piece!r}") from None
        if t1 == t2:
            raise ValueError(f"时段起止相同: {piece!r}")
        segs.append((t1, t2))
    if not segs:
        raise ValueError("营业时段为空")
    return segs


def parse_weekday(tok: str) -> int:
    t = tok.strip().lower()
    if t in WD_NUM:
        return WD_NUM[t]
    for i, zh in enumerate("一二三四五六日", start=1):
        if t in (zh, f"周{zh}", f"星期{zh}"):
            return i
    if t.isdigit() and 1 <= int(t) <= 7:
        return int(t)
    raise ValueError(f"无法识别星期: {tok!r}")


def parse_weekends(spec: str) -> set:
    if spec.strip().lower() in ("none", "无"):
        return set()
    return {parse_weekday(tok) for tok in spec.split(",") if tok.strip()}


def parse_closed(specs) -> set:
    def full(t: str) -> date:
        try:
            return date.fromisoformat(t.strip())
        except ValueError:
            raise ValueError(f"无效日期(需 YYYY-MM-DD): {t}") from None

    out = set()
    for item in specs:
        for piece in str(item).split(","):
            piece = piece.strip()
            if not piece:
                continue
            if ".." in piece:
                a, _, b = piece.partition("..")
                d1, d2 = full(a), full(b)
                if d2 < d1:
                    raise ValueError(f"日期区间倒序: {piece}")
                if (d2 - d1).days > 400:
                    raise ValueError(f"日期区间过长(>400 天): {piece}")
                cur = d1
                while cur <= d2:
                    out.add(cur)
                    cur += timedelta(days=1)
            else:
                out.add(full(piece))
    return out


def split_by_day(lo: datetime, hi: datetime, bucket: dict) -> None:
    """把 [lo,hi] 的重叠时长按自然日拆分累进 bucket[date]。"""
    day0 = lo.date()
    while day0 <= hi.date():
        seg_lo = max(lo, datetime.combine(day0, time(0, 0)))
        seg_hi = min(hi, datetime.combine(day0, time(0, 0)) + timedelta(days=1))
        if seg_hi > seg_lo:
            bucket[day0] = bucket.get(day0, 0.0) + (seg_hi - seg_lo).total_seconds()
        day0 += timedelta(days=1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="按自定义营业时段计算两时刻之间的有效营业小时数")
    parser.add_argument("start", help="起始时刻 YYYY-MM-DD[ HH:MM[:SS]]")
    parser.add_argument("end", help="结束时刻 YYYY-MM-DD[ HH:MM[:SS]]")
    parser.add_argument("--hours", default="09:00-18:00", metavar="SPEC",
                        help="每日营业时段，如 09:00-12:00,13:00-18:00（默认 09:00-18:00）")
    parser.add_argument("--weekend", default="sat,sun", metavar="LIST",
                        help="每周休息日（默认 sat,sun；none 表示无周休）")
    parser.add_argument("--closed", action="append", default=[], metavar="D",
                        help="额外歇业日 YYYY-MM-DD 或 A..B，可重复或逗号分隔")
    parser.add_argument("--detail", action="store_true", help="按日打印明细")
    args = parser.parse_args(argv)

    try:
        start = parse_dt(args.start)
        end = parse_dt(args.end)
        segs = parse_hours(args.hours)
        # parse_weekday 返回 ISO 1-7(周一=1)，转成 weekday() 口径 0-6(周一=0)
        weekends = {i - 1 for i in parse_weekends(args.weekend)}
        closed = parse_closed(args.closed)
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    if end < start:
        print(f"错误: 结束时刻早于起始时刻 ({args.end} < {args.start})", file=sys.stderr)
        return 2

    # 逐日展开营业区间（多扩一天以覆盖跨午夜时段的溢出），与 [start,end] 求交
    intervals = []
    d = start.date() - timedelta(days=1)
    last = end.date() + timedelta(days=1)
    while d <= last:
        if d.weekday() not in weekends and d not in closed:
            for t1, t2 in segs:
                s = datetime.combine(d, t1)
                e = datetime.combine(d, t2)
                if e <= s:
                    e += timedelta(days=1)  # 跨午夜时段
                lo, hi = max(s, start), min(e, end)
                if hi > lo:
                    intervals.append((lo, hi))
        d += timedelta(days=1)

    bucket = {}
    for lo, hi in intervals:
        split_by_day(lo, hi, bucket)
    total = sum(bucket.values())

    seg_txt = " / ".join(f"{t1:%H:%M}-{t2:%H:%M}" for t1, t2 in segs)
    wk_txt = "、".join("周" + "一二三四五六日"[i] for i in sorted(weekends)) or "无"
    cj_txt = "、".join(d.isoformat() for d in sorted(closed)) or "无"
    print(f"统计区间 : {start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M}")
    print(f"营业时段 : {seg_txt}")
    print(f"周休     : {wk_txt} ；节假日: {cj_txt}")
    print(f"有效营业 : {total / 3600:.2f} 小时 ({total / 60:.0f} 分钟)")

    if args.detail:
        print("按日明细:")
        d = start.date()
        while d <= end.date():
            sec = bucket.get(d, 0.0)
            if d in closed:
                tag = "节假日"
            elif d.weekday() in weekends:
                tag = "周末休"
            else:
                tag = "工作日"
            print(f"  {d} {WD_ZH[d.weekday()]}  {tag}  {sec / 3600:6.2f} h")
            d += timedelta(days=1)
    return 0


if __name__ == "__main__":
    _setup_stdio()
    sys.exit(main())
