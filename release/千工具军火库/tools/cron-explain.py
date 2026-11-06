#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cron 表达式释义 —— 把 cron 五段表达式翻译成中文人话描述其触发规律。

用法:
    python cron-explain.py "*/15 9-17 * * 1-5"
    python cron-explain.py "0 9 1 * *" "30 4 * * mon-fri"

对每个字段给出中文含义, 并合成整句"人话"描述。支持 * 、列表、区间
a-b、步长 */n、月份与星期英文名 (jan-dec / sun-sat, 7=周日) 以及
@daily 等别名。日(dom) 与星期(dow) 同时受限时按 vixie cron 语义取
并集 (任一匹配即触发), 输出中会注明。

仅使用 Python 标准库 (3.8+)。
"""

from __future__ import annotations

import argparse
import sys

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
WEEKS = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
WEEK_CRON_CN = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]  # 下标=cron 星期值(0=周日)
ALIASES = {"@hourly": "0 * * * *", "@daily": "0 0 * * *", "@midnight": "0 0 * * *",
           "@weekly": "0 0 * * 0", "@monthly": "0 0 1 * *",
           "@yearly": "0 0 1 1 *", "@annually": "0 0 1 1 *"}


class CronError(ValueError):
    pass


def _setup_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_field(field: str, lo: int, hi: int, names, kind: str,
                is_dow: bool = False) -> set:
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
            hi_b = hi if slash else lo_b
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


def arith_step(vs: list):
    """若有序列表为等差数列则返回公差, 否则 None。"""
    if len(vs) >= 3:
        step = vs[1] - vs[0]
        if step >= 1 and all(vs[i + 1] - vs[i] == step for i in range(len(vs) - 1)):
            return step
    return None


def join_cn(items: list, limit: int = 8) -> str:
    if len(items) <= limit:
        return "、".join(items)
    return "、".join(items[:limit]) + " 等"


def minute_desc(vals) -> str:
    vs = sorted(vals)
    if len(vs) == 60:
        return "每分钟"
    step = arith_step(vs)
    if step == 1:
        return f"第 {vs[0]} 到 {vs[-1]} 分" if len(vs) > 1 else f"第 {vs[0]} 分"
    if step:
        if vs[0] == 0 and vs[-1] + step > 59:
            return f"每 {step} 分钟"
        return f"第 {vs[0]} 到 {vs[-1]} 分之间每 {step} 分钟"
    return "第 " + join_cn([str(v) for v in vs]) + " 分"


def hour_desc(vals) -> str:
    vs = sorted(vals)
    if len(vs) == 24:
        return "每小时"
    step = arith_step(vs)
    if step == 1:
        return f"{vs[0]} 时到 {vs[-1]} 时" if len(vs) > 1 else f"{vs[0]} 时"
    if step:
        if vs[0] == 0 and vs[-1] + step > 23:
            return f"每 {step} 小时"
        return f"{vs[0]} 时到 {vs[-1]} 时之间每 {step} 小时"
    return join_cn([f"{v} 时" for v in vs])


def dom_desc(vals) -> str:
    vs = sorted(vals)
    if len(vs) == 31:
        return "每天"
    step = arith_step(vs)
    if step == 1:
        return f"每月 {vs[0]} 到 {vs[-1]} 日" if len(vs) > 1 else f"每月 {vs[0]} 日"
    if step:
        return f"每月 {vs[0]} 到 {vs[-1]} 日之间每 {step} 天"
    return "每月 " + join_cn([f"{v} 日" for v in vs])


def month_desc(vals) -> str:
    vs = sorted(vals)
    if len(vs) == 12:
        return "每月"
    step = arith_step(vs)
    if step == 1:
        return f"{vs[0]} 月到 {vs[-1]} 月" if len(vs) > 1 else f"{vs[0]} 月"
    return join_cn([f"{v} 月" for v in vs])


def dow_desc(vals) -> str:
    vs = sorted(vals)
    if len(vs) == 7:
        return "不限星期几"
    step = arith_step(vs)
    if step == 1 and len(vs) > 1:
        return f"每{WEEK_CRON_CN[vs[0]]} 到 {WEEK_CRON_CN[vs[-1]]}"
    items = [f"每{WEEK_CRON_CN[vs[0]]}"] + [WEEK_CRON_CN[v] for v in vs[1:]]
    return join_cn(items)


def time_desc(hour_vals, minute_vals) -> str:
    hs, ms = sorted(hour_vals), sorted(minute_vals)
    h_full, m_full = len(hs) == 24, len(ms) == 60
    if h_full and m_full:
        return "每分钟"
    if h_full:
        return minute_desc(ms)
    h_phrase = hour_desc(hs)
    if m_full:
        return f"{h_phrase} 内每分钟"
    step = arith_step(ms)
    if step and step > 1:
        suffix = f"(自第 {ms[0]} 分起)" if ms[0] else ""
        return f"{h_phrase}之间每 {step} 分钟{suffix}"
    if len(hs) * len(ms) <= 6:
        return "在 " + "、".join(f"{h:02d}:{m:02d}" for h in hs for m in ms)
    return f"{h_phrase}, 分钟{minute_desc(ms)}"


def describe(cron: dict) -> str:
    segs = []
    md = month_desc(cron["month"])
    if md != "每月":
        segs.append(md)
    if cron["dom_star"] and cron["dow_star"]:
        segs.append("每天")
    else:
        parts = []
        if not cron["dom_star"]:
            parts.append(dom_desc(cron["dom"]))
        if not cron["dow_star"]:
            parts.append(dow_desc(cron["dow"]))
        if len(parts) == 2:
            segs.append(" 或 ".join(parts) + "(日与星期任一匹配即触发)")
        else:
            segs.append(parts[0])
    segs.append(time_desc(cron["hour"], cron["minute"]))
    tail = segs[-1]
    return "，".join(segs) + (" 执行一次" if tail.startswith("在") else "执行一次")


def main(argv=None) -> int:
    _setup_streams()
    p = argparse.ArgumentParser(
        prog="cron-explain",
        description="把 cron 五段表达式翻译成中文人话描述其触发规律")
    p.add_argument("exprs", nargs="+",
                   help="五段 cron 表达式 (可一次给多个) 或 @daily 等别名")
    args = p.parse_args(argv)

    rc = 0
    for raw in args.exprs:
        e = raw.strip()
        note = ""
        low = e.lower()
        if low in ALIASES:
            note = f"   (别名 {e} ⇒ {ALIASES[low]})"
            e = ALIASES[low]
        try:
            cron = parse_expr(e)
        except CronError as exc:
            print(f"表达式: {raw}\n  错误: {exc}\n")
            rc = 2
            continue
        print(f"表达式: {e}{note}")
        print(f"  分钟 : {minute_desc(cron['minute'])}  [{len(cron['minute'])} 个取值]")
        print(f"  小时 : {hour_desc(cron['hour'])}  [{len(cron['hour'])} 个取值]")
        print(f"  日   : {'* (不限)' if cron['dom_star'] else dom_desc(cron['dom'])}")
        print(f"  月   : {month_desc(cron['month'])}")
        print(f"  星期 : {'* (不限)' if cron['dow_star'] else dow_desc(cron['dow'])}")
        print(f"人话  : {describe(cron)}")
        print()
    return rc


if __name__ == "__main__":
    sys.exit(main())
