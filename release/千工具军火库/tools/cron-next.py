#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cron 未来执行推算 —— 解析 crontab 表达式并计算未来 N 次执行时间。

用法:
    python cron-next.py "*/15 9-17 * * 1-5" -n 5
    python cron-next.py "30 4 1,15 * *" --from "2026-11-02 08:00" -n 3
    python cron-next.py "@daily" -n 2

支持标准五段表达式 (分 时 日 月 周): * 、列表 、区间 a-b 、步长
*(或区间)/n , 月份与星期支持英文名 (jan-dec / sun-sat, 大小写不敏感,
星期 7=周日); 兼容 @hourly/@daily/@midnight/@weekly/@monthly/@yearly/
@annually 别名。日(dom) 与星期(dow) 同时受限时按 vixie cron 语义取并集
(任一匹配即触发)。结果为本地时间且严格晚于起点 (--from, 缺省当前时间);
按分钟精度计算, 不考虑夏令时切换。

仅使用 Python 标准库 (3.8+)。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
WEEKS = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
WEEK_LOCAL_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]  # 下标=Python weekday()
ALIASES = {"@hourly": "0 * * * *", "@daily": "0 0 * * *", "@midnight": "0 0 * * *",
           "@weekly": "0 0 * * 0", "@monthly": "0 0 1 * *",
           "@yearly": "0 0 1 1 *", "@annually": "0 0 1 1 *"}
_MAX_DAYS = 20000


class CronError(ValueError):
    pass


def _setup_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_field(field: str, lo: int, hi: int, names, kind: str,
                is_dow: bool = False) -> set:
    """解析单个 cron 字段为取值集合; 星期域把 7 归一化为 0 (周日)。"""

    def resolve(tok: str) -> int:
        tok = tok.strip().lower()
        if tok.isdigit():
            return int(tok)
        if names and tok in names:
            return names[tok]
        raise CronError(f"{kind}字段取值非法: {tok!r}")

    vals = set()
    for term in field.split(","):
        term = term.strip()
        if not term:
            raise CronError(f"{kind}字段存在空项: {field!r}")
        base, slash, step_s = term.partition("/")
        step = 1
        if slash:
            try:
                step = int(step_s)
            except ValueError:
                raise CronError(f"{kind}字段步长非法: {term!r}")
            if step < 1:
                raise CronError(f"{kind}字段步长必须 >= 1: {term!r}")
        if base == "*":
            lo_b, hi_b = lo, hi
        elif "-" in base:
            a, _, b = base.partition("-")
            lo_b, hi_b = resolve(a), resolve(b)
        else:
            lo_b = resolve(base)
            hi_b = hi if slash else lo_b  # vixie 语义: n/step 视为 n-max/step
        if lo_b > hi_b:
            raise CronError(f"{kind}字段区间反序: {term!r}")
        if lo_b < lo or hi_b > hi:
            raise CronError(f"{kind}字段取值超出 {lo}-{hi} 范围: {term!r}")
        vals.update(range(lo_b, hi_b + 1, step))
    if is_dow:
        vals = {0 if v == 7 else v for v in vals}
    return vals


def parse_expr(expr: str) -> dict:
    e = expr.strip()
    note = ""
    low = e.lower()
    if low in ALIASES:
        note = f"   (别名 {e} ⇒ {ALIASES[low]})"
        e = ALIASES[low]
    parts = e.split()
    if len(parts) != 5:
        raise CronError(f"表达式需要 5 段 (分 时 日 月 周), "
                        f"实得 {len(parts)} 段: {expr.strip()!r}")
    return {
        "minute": parse_field(parts[0], 0, 59, None, "分钟"),
        "hour": parse_field(parts[1], 0, 23, None, "小时"),
        "dom": parse_field(parts[2], 1, 31, None, "日"),
        "month": parse_field(parts[3], 1, 12, MONTHS, "月"),
        "dow": parse_field(parts[4], 0, 7, WEEKS, "星期", is_dow=True),
        "dom_star": parts[2] == "*",
        "dow_star": parts[4] == "*",
        "note": note,
    }


def parse_from(text: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    raise CronError(f"无法解析 --from 时间: {text!r}")


def day_ok(d, cron: dict) -> bool:
    if d.month not in cron["month"]:
        return False
    dom_ok = (not cron["dom_star"]) and d.day in cron["dom"]
    dow_ok = (not cron["dow_star"]) and (d.weekday() + 1) % 7 in cron["dow"]
    if cron["dom_star"] and cron["dow_star"]:
        return True
    if cron["dom_star"]:
        return dow_ok
    if cron["dow_star"]:
        return dom_ok
    return dom_ok or dow_ok


def next_runs(cron: dict, start: datetime, n: int) -> list:
    results = []
    t = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
    hours = sorted(cron["hour"])
    minutes = sorted(cron["minute"])
    d = t.date()
    for _ in range(_MAX_DAYS):
        if day_ok(d, cron):
            for h in hours:
                for m in minutes:
                    cand = datetime(d.year, d.month, d.day, h, m)
                    if cand >= t:
                        results.append(cand)
                        if len(results) >= n:
                            return results
        d += timedelta(days=1)
    return results


def main(argv=None) -> int:
    _setup_streams()
    p = argparse.ArgumentParser(
        prog="cron-next",
        description="解析 crontab 五段表达式并计算未来 N 次执行时间")
    p.add_argument("expr", help="五段 cron 表达式, 或 @hourly/@daily 等别名")
    p.add_argument("-n", "--count", type=int, default=5, help="列出未来 N 次 (默认 5)")
    p.add_argument("--from", dest="from_time",
                   help="推算起点, 如 '2026-11-02 08:00'; 缺省为当前时间 (结果严格晚于起点)")
    args = p.parse_args(argv)

    try:
        cron = parse_expr(args.expr)
        start = parse_from(args.from_time) if args.from_time else datetime.now()
        runs = next_runs(cron, start, max(1, args.count))
    except CronError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    print(f"表达式: {args.expr.strip()}{cron['note']}")
    print(f"起点  : {start.strftime('%Y-%m-%d %H:%M:%S')} 之后 (严格晚于)")
    if not runs:
        print(f"结果  : {_MAX_DAYS} 天 (~54 年) 内没有匹配的执行时间, "
              "表达式可能永不满足 (例如 2 月 30 日)")
        return 1
    print(f"未来 {len(runs)} 次执行 (本地时间):")
    for i, dt in enumerate(runs, 1):
        print(f"  {i}. {dt.strftime('%Y-%m-%d %H:%M')} ({WEEK_LOCAL_CN[dt.weekday()]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
