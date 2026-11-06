#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cron 表达式解释 (cron-describe)。

用途:
    解析标准五段式 cron 表达式（分 时 日 月 周），输出各字段中文含义
    与未来 N 次触发时间。支持 * 、数字、列表(,)、区间(-)、步长(/)；
    星期 0 和 7 均表示周日。

示例命令:
    python -I cron-describe.py "30 8 * * 1-5" -n 5
    python -I cron-describe.py "*/15 * * * *" --from "2026-11-01 00:00:00" --json
    python -I cron-describe.py --self-test
"""
import argparse
import json
import sys
from datetime import datetime, timedelta

WEEK_CN = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]
FIELD_CN = ["分", "时", "日", "月", "周"]
RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
MAX_DAY_SCAN = 5000  # 最多向后扫描的天数


def weekday_cn(dt: datetime) -> str:
    """Python weekday()（周一=0）→ cron 周序（周日=0）→ 中文名。"""
    return WEEK_CN[(dt.weekday() + 1) % 7]


def parse_field(field: str, lo: int, hi: int) -> set:
    """解析单字段为合法值集合；周字段 7 归一为 0。"""
    vals = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"空字段片段: {field!r}")
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            step = int(step_s)
            if step <= 0:
                raise ValueError(f"步长必须为正: {field!r}")
        if part == "*" or part == "":
            start, end = lo, hi
        elif "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
        else:
            start = end = int(part)
            if "/" in field and step > 1:
                end = hi  # "5/15" 形式：从 5 起按步长到上限
        if start < lo or end > hi or start > end:
            raise ValueError(f"字段超出范围 [{lo},{hi}]: {part!r} in {field!r}")
        vals.update(range(start, end + 1, step))
    if hi == 7:  # 周字段: 7 归一为 0(周日)
        return {0 if v == 7 else v for v in vals}
    return vals


def parse_cron(expr: str):
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"需要 5 个字段，得到 {len(fields)} 个: {expr!r}")
    sets = []
    for f, (lo, hi) in zip(fields, RANGES):
        sets.append(parse_field(f, lo, hi))
    # 周字段特例：若 0 与 7 同时视为周日，无需去重处理（集合已归一）
    return fields, sets


def _list_cn(vals: set, lo: int, hi: int, unit: str, week=False) -> str:
    if len(vals) == hi - lo + 1:
        return f"每{unit}" if not week else "每周"
    def name(v):
        return WEEK_CN[v % 7] if week else str(v)
    s = sorted(vals)
    # 连续区间压缩
    parts, i = [], 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[j] + 1:
            j += 1
        if j > i and not week:
            parts.append(f"{s[i]}-{s[j]}" if s[i] != lo or s[j] != hi else f"每{unit}")
        elif j > i and week:
            parts.append(f"{name(s[i])}至{name(s[j])}")
        else:
            parts.append(name(s[i]))
        i = j + 1
    return "、".join(parts)


def describe(expr: str) -> str:
    fields, sets = parse_cron(expr)
    minute, hour, dom, month, dow = sets
    desc = [f"{cn}：{_list_cn(s, lo, hi, cn, week=(i == 4))}"
            for i, (cn, s, (lo, hi)) in enumerate(zip(FIELD_CN, sets, RANGES))]
    head = " ".join(fields)
    return f"表达式 {head} → " + "；".join(desc)


def next_runs(expr: str, start: datetime, n: int):
    fields, sets = parse_cron(expr)
    minutes, hours, doms, months, dows = sets
    dom_wild = fields[2] == "*"
    dow_wild = fields[4] == "*"
    day = start.date()
    t = start.replace(second=0, microsecond=0)
    results = []
    for _ in range(MAX_DAY_SCAN):
        if day.month not in months:
            # 跳到下月一号
            y, m = day.year, day.month
            m += 1
            if m > 12:
                m, y = 1, y + 1
            day = datetime(y, m, 1).date()
            continue
        dom_hit = day.day in doms
        dow_hit = (day.weekday() + 1) % 7 in dows
        # 标准 cron 语义：日与周同时受限时取并集，否则按所限字段
        if dom_wild:
            day_ok = dow_hit
        elif dow_wild:
            day_ok = dom_hit
        else:
            day_ok = dom_hit or dow_hit
        if day_ok:
            for h in sorted(hours):
                for mi in sorted(minutes):
                    cand = datetime(day.year, day.month, day.day, h, mi)
                    if cand > t:
                        results.append(cand)
                        if len(results) >= n:
                            return results
        day += timedelta(days=1)
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description="解释 cron 五段表达式并给出未来触发时间")
    ap.add_argument("expr", nargs="?", help="cron 表达式，如 \"30 8 * * 1-5\"")
    ap.add_argument("-n", "--count", type=int, default=3, help="显示未来触发次数（默认 3）")
    ap.add_argument("--from", dest="start", metavar="DATETIME",
                    help="起始时间 \"YYYY-MM-DD[ HH:MM[:SS]]\"（默认当前时间）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--self-test", action="store_true", help="运行内置自测")
    args = ap.parse_args(argv)

    if args.self_test:
        assert parse_field("*", 0, 59) == set(range(60))
        assert parse_field("*/15", 0, 59) == set(range(0, 60, 15))
        assert parse_field("1-5", 1, 12) == {1, 2, 3, 4, 5}
        assert parse_field("0,30", 0, 59) == {0, 30}
        w = parse_field("1-5", 0, 7)
        assert w == {1, 2, 3, 4, 5}, w
        assert 0 in parse_field("0", 0, 7)
        runs = next_runs("30 8 * * *", datetime(2026, 11, 1, 9, 0), 2)
        assert runs[0] == datetime(2026, 11, 2, 8, 30), runs
        assert runs[1] == datetime(2026, 11, 3, 8, 30), runs
        runs2 = next_runs("*/15 * * * *", datetime(2026, 11, 1, 0, 0), 3)
        assert runs2 == [datetime(2026, 11, 1, 0, 15),
                         datetime(2026, 11, 1, 0, 30),
                         datetime(2026, 11, 1, 0, 45)], runs2
        runs3 = next_runs("0 0 * * 0", datetime(2026, 11, 1, 0, 0), 1)  # 周日
        assert runs3[0].weekday() == 6, runs3
        d = describe("30 8 * * 1-5")
        assert "周一" in d and "周五" in d and "30" in d and "8" in d, d
        # 显示路径回归：weekday_cn 必须与真实日历一致
        # （2026-11-05=周四、11-06=周五、11-07=周六、11-08=周日、11-09=周一）
        assert weekday_cn(datetime(2026, 11, 5)) == "周四"
        assert weekday_cn(datetime(2026, 11, 6)) == "周五"
        assert weekday_cn(datetime(2026, 11, 7)) == "周六"
        assert weekday_cn(datetime(2026, 11, 8)) == "周日"
        assert weekday_cn(datetime(2026, 11, 9)) == "周一"
        print("self-test OK")
        return 0

    if not args.expr:
        ap.error("缺少 cron 表达式；例如: cron-describe.py \"30 8 * * 1-5\"")

    try:
        desc = describe(args.expr)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2

    start = datetime.now()
    if args.start:
        for pat in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                start = datetime.strptime(args.start, pat)
                break
            except ValueError:
                continue
        else:
            print(f"错误: 无法解析起始时间 {args.start!r}", file=sys.stderr)
            return 2

    runs = next_runs(args.expr, start, max(0, args.count))
    if args.json:
        print(json.dumps({
            "expr": " ".join(args.expr.split()),
            "description": desc,
            "from": start.strftime("%Y-%m-%d %H:%M:%S"),
            "next": [r.strftime("%Y-%m-%d %H:%M") for r in runs],
        }, ensure_ascii=False, indent=2))
    else:
        print(desc)
        if runs:
            print(f"未来 {len(runs)} 次触发（自 {start.strftime('%Y-%m-%d %H:%M:%S')} 起）:")
            for i, r in enumerate(runs, 1):
                print(f"  {i}. {r.strftime('%Y-%m-%d %H:%M')} ({weekday_cn(r)})")
        else:
            print("未找到未来触发时间（检查 日/周 组合是否可能成立）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
