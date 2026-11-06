#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重复事件展开 —— 解析 .ics 中的 RRULE 规则并展开为具体日期实例。

用途:
    读取 iCalendar 文件, 找出其中所有 VEVENT, 将 RRULE 规则展开为具体的
    发生时间并逐条列出 (无 RRULE 的事件列出 DTSTART 本身)。支持
    FREQ=DAILY/WEEKLY/MONTHLY/YEARLY 以及 INTERVAL/COUNT/UNTIL/BYDAY
    (含 1MO、-1FR 序数形式)/BYMONTHDAY/BYMONTH, 并按 EXDATE 剔除例外。
    DTSTART 带 TZID 或以 Z 结尾时按墙钟值原样展开, 不做时区换算。

示例:
    python ics-rrule.py event.ics
    python ics-rrule.py event.ics --limit 5
    python ics-rrule.py event.ics --only evt-1@selftest

仅使用 Python 标准库 (3.8+)。
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta

WEEKDAY_NUM = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
_PERIOD = {"DAILY": 1, "WEEKLY": 7, "MONTHLY": 31, "YEARLY": 366}
_MAX_SCAN_DAYS = 20000


def _setup_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def unfold(text: str) -> list:
    """RFC 5545 解折行: 以空格/制表符开头的行并入上一行。"""
    lines = []
    for raw in text.splitlines():
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def parse_line(line: str):
    """拆出 (属性名, 参数dict, 值); 无法解析返回 None。"""
    i = line.find(":")
    if i < 0:
        return None
    head, value = line[:i], line[i + 1:]
    segs = head.split(";")
    params = {}
    for seg in segs[1:]:
        if "=" in seg:
            k, v = seg.split("=", 1)
            params[k.upper()] = v
    return segs[0].upper(), params, value


def parse_ics_dt(value: str, params: dict):
    """解析 DTSTART/EXDATE/UNTIL 值, 返回 (datetime, 是否纯日期, 是否UTC)。"""
    v = value.strip()
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", v):
        return datetime.strptime(v, "%Y%m%d"), True, False
    is_utc = v.endswith("Z")
    if is_utc:
        v = v[:-1]
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(v, fmt), False, is_utc
        except ValueError:
            continue
    raise ValueError(f"无法解析日期时间: {value!r}")


def parse_rrule(value: str) -> dict:
    rule = {}
    for part in value.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            rule[k.strip().upper()] = v.strip()
    return rule


def parse_byday(value: str) -> list:
    out = []
    for tok in value.split(","):
        m = re.fullmatch(r"([+-]?\d+)?([A-Za-z]{2})", tok.strip())
        if not m or m.group(2).upper() not in WEEKDAY_NUM:
            raise ValueError(f"无法解析 BYDAY 项: {tok!r}")
        out.append((int(m.group(1)) if m.group(1) else None,
                    WEEKDAY_NUM[m.group(2).upper()]))
    return out


def split_events(lines: list) -> list:
    """抽出各 VEVENT 的属性列表 [(name, params, value), ...]。"""
    events, cur = [], None
    for line in lines:
        parsed = parse_line(line)
        name = parsed[0] if parsed else ""
        value = parsed[2].strip().upper() if parsed else ""
        if name == "BEGIN" and value == "VEVENT":
            cur = []
        elif name == "END" and value == "VEVENT" and cur is not None:
            events.append(cur)
            cur = None
        elif cur is not None and parsed is not None:
            cur.append(parsed)
    return events


def first_prop(props, name):
    for nm, params, value in props:
        if nm == name:
            return params, value
    return {}, None


def collect_exdates(props):
    ex_dt, ex_date = set(), set()
    for nm, params, value in props:
        if nm != "EXDATE":
            continue
        for v in value.split(","):
            v = v.strip()
            if not v:
                continue
            try:
                dt, date_only, _ = parse_ics_dt(v, params)
            except ValueError:
                continue
            if date_only:
                ex_date.add(dt.date())
            else:
                ex_dt.add(dt)
    return ex_dt, ex_date


def build_matcher(rule: dict, start: datetime):
    freq = rule.get("FREQ", "").upper()
    if freq not in _PERIOD:
        raise ValueError(f"暂不支持的 FREQ: {rule.get('FREQ', '(缺失)')!r}")
    interval = max(1, int(rule.get("INTERVAL", "1") or 1))
    bymonth = [int(x) for x in rule.get("BYMONTH", "").split(",") if x.strip()]
    bymonthday = [int(x) for x in rule.get("BYMONTHDAY", "").split(",") if x.strip()]
    byday = parse_byday(rule["BYDAY"]) if "BYDAY" in rule else None

    ord0 = start.toordinal()
    monday0 = ord0 - start.weekday()

    def nth_weekday_hit(d, n, wd):
        if n > 0:
            first = d.replace(day=1)
            day = 1 + (wd - first.weekday()) % 7 + (n - 1) * 7
        else:
            nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
            last = nxt - timedelta(days=1)
            day = last.day - (last.weekday() - wd) % 7 - (-n - 1) * 7
        return d.day == day

    def match(d):
        if bymonth and d.month not in bymonth:
            return False
        if freq == "DAILY":
            if (d.toordinal() - ord0) % interval:
                return False
            if bymonthday and d.day not in bymonthday:
                return False
            if byday and d.weekday() not in {wd for _, wd in byday}:
                return False
            return True
        if freq == "WEEKLY":
            monday_d = d.toordinal() - d.weekday()
            if ((monday_d - monday0) // 7) % interval:
                return False
            wanted = {wd for _, wd in byday} if byday else {start.weekday()}
            return d.weekday() in wanted
        if freq == "MONTHLY":
            months = (d.year - start.year) * 12 + (d.month - start.month)
            if months % interval:
                return False
            if bymonthday:
                return d.day in bymonthday
            if byday:
                return any((d.weekday() == wd if n is None
                            else nth_weekday_hit(d, n, wd)) for n, wd in byday)
            return d.day == start.day
        # YEARLY
        if (d.year - start.year) % interval:
            return False
        if d.month not in (bymonth or [start.month]):
            return False
        if bymonthday:
            return d.day in bymonthday
        if byday:
            return any((d.weekday() == wd if n is None
                        else nth_weekday_hit(d, n, wd)) for n, wd in byday)
        return d.day == start.day

    return match, interval, freq


def expand(start: datetime, date_only: bool, rule: dict, limit: int,
           ex_dt: set, ex_date: set) -> list:
    match, interval, freq = build_matcher(rule, start)
    count = int(rule["COUNT"]) if "COUNT" in rule else None
    until = None
    if "UNTIL" in rule:
        until, _, _ = parse_ics_dt(rule["UNTIL"], {})

    horizon = (start + timedelta(
        days=min(_MAX_SCAN_DAYS, limit * interval * _PERIOD[freq] + 400))).date()
    if until is not None:
        horizon = min(horizon, until.date())

    matched = []
    d = start.date()
    while d <= horizon:
        if count is not None and len(matched) >= count:
            break
        if match(d):
            matched.append(d)
        d += timedelta(days=1)

    instances = []
    for d in matched:
        if date_only:
            if d in ex_date:
                continue
            if until is not None and d > until.date():
                continue
            instances.append(d)
        else:
            inst = datetime.combine(d, start.time())
            if inst in ex_dt or d in ex_date:
                continue
            if until is not None and inst > until:
                continue
            instances.append(inst)
    return instances[:limit]


def fmt_inst(inst, date_only: bool) -> str:
    if date_only:
        return inst.strftime("%Y-%m-%d (全天)")
    if inst.second or inst.microsecond:
        return inst.strftime("%Y-%m-%d %H:%M:%S")
    return inst.strftime("%Y-%m-%d %H:%M")


def main(argv=None) -> int:
    _setup_streams()
    p = argparse.ArgumentParser(
        prog="ics-rrule",
        description="解析 .ics 中的 RRULE 规则并展开为具体日期实例")
    p.add_argument("input", help="输入的 .ics 文件")
    p.add_argument("--limit", type=int, default=10,
                   help="每个事件最多列出的实例数 (默认 10)")
    p.add_argument("--only", help="只处理 UID 以该前缀开头的事件")
    args = p.parse_args(argv)
    limit = max(1, args.limit)

    try:
        with open(args.input, "r", encoding="utf-8-sig", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"错误: 读取 {args.input} 失败: {exc}", file=sys.stderr)
        return 1

    events = split_events(unfold(text))
    if not events:
        print("未找到任何 VEVENT")
        return 0

    shown = 0
    for idx, props in enumerate(events, 1):
        params, dtstart_raw = first_prop(props, "DTSTART")
        _, uid = first_prop(props, "UID")
        _, summary = first_prop(props, "SUMMARY")
        uid = uid or f"(无UID #{idx})"
        summary = summary or "(无标题)"
        if args.only and not uid.startswith(args.only):
            continue
        print(f"[{idx}] {summary} (UID: {uid})")
        shown += 1
        if dtstart_raw is None:
            print("    缺少 DTSTART, 跳过")
            continue
        try:
            start, date_only, is_utc = parse_ics_dt(dtstart_raw, params)
        except ValueError as exc:
            print(f"    {exc}, 跳过")
            continue
        if date_only:
            print(f"    DTSTART: {start.strftime('%Y-%m-%d')} (全天)")
        else:
            tz = " UTC" if is_utc else (
                f" (TZID={params['TZID']}, 按墙钟展开)" if "TZID" in params else "")
            print(f"    DTSTART: {start}{tz}")
        _, rrule_raw = first_prop(props, "RRULE")
        if rrule_raw is None:
            print("    无 RRULE, 仅 DTSTART 一次, 实例 1 个:")
            print(f"      1. {fmt_inst(start, date_only)}")
            continue
        print(f"    RRULE: {rrule_raw}")
        ex_dt, ex_date = collect_exdates(props)
        if ex_dt or ex_date:
            print(f"    EXDATE 共 {len(ex_dt) + len(ex_date)} 个 (命中的已剔除)")
        try:
            instances = expand(start, date_only, parse_rrule(rrule_raw),
                               limit, ex_dt, ex_date)
        except (ValueError, OverflowError) as exc:
            print(f"    展开失败: {exc}")
            continue
        print(f"    展开实例 {len(instances)} 个:")
        for i, inst in enumerate(instances, 1):
            print(f"      {i}. {fmt_inst(inst, date_only)}")

    if not shown:
        print("没有匹配 --only 条件的事件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
