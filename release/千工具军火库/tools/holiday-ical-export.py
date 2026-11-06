#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""节假日 iCal 导出 —— 把某年节假日列表生成为 .ics 日历文件（RFC 5545
全天事件，CRLF + 75 字节折行），可直接导入 Outlook / Google 日历 /
Apple 日历 / 网易邮箱日历等主流日历应用。

用法:
    python holiday-ical-export.py 2027 --day 01-01:元旦 --day 05-01:劳动节 --out cn-2027.ics
    python holiday-ical-export.py 2027 --day 10-01..10-07:国庆节 --name "2027 假期"
    python holiday-ical-export.py 2027 --json holidays.json

--day 参数（可重复给出多组）:
    MM-DD[:名称]          当年日期，名称缺省为“节假日”
    MM-DD..MM-DD[:名称]   日期区间（含两端），共用同一名称
    YYYY-MM-DD[:名称]     显式年份日期（此时年份参数可省略）
--json 参数: JSON 文件，内容为数组
    [{"date": "2027-01-01", "name": "元旦"}, ...]
    或对象 {"2027-01-01": "元旦", ...}（值为 null 时用缺省名称）。

示例输出:
    $ python holiday-ical-export.py 2027 --day 01-01:元旦 --out cn-2027.ics
    已写入 1 个全天事件 -> cn-2027.ics (约 240 字节)
    事件预览: 01-01 元旦

退出码: 0 成功; 2 参数、日期或 JSON 格式错误。
仅用 Python 标准库，单文件。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone

PRODID = "-//tool-armory//holiday-ical-export 1.0//CN"
DEFAULT_NAME = "节假日"


def _setup_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _to_date(text: str, year) -> date:
    """解析 MM-DD（依赖 year）或 YYYY-MM-DD，失败抛 ValueError。"""
    t = text.strip()
    parts = t.split("-")
    if len(parts) == 2:
        if year is None:
            raise ValueError(f"{t}: 缺少年份，请改用 YYYY-MM-DD 或给出年份参数")
        try:
            return date(year, int(parts[0]), int(parts[1]))
        except ValueError:
            raise ValueError(f"无效日期: {t}") from None
    try:
        return date.fromisoformat(t)
    except ValueError:
        raise ValueError(f"无效日期: {t}") from None


def add_day_spec(spec: str, year, events: dict) -> None:
    """解析一条 --day 参数（MM-DD[:名称] 或 A..B[:名称]），合并进 events。"""
    body, sep, name = spec.partition(":")
    name = (name.strip() or DEFAULT_NAME) if sep else DEFAULT_NAME
    if ".." in body:
        a, _, b = body.partition("..")
        d1 = _to_date(a, year)
        d2 = _to_date(b, year)
        if d2 < d1:
            raise ValueError(f"日期区间倒序: {spec}")
        if (d2 - d1).days > 400:
            raise ValueError(f"日期区间过长(>400 天): {spec}")
        cur = d1
        while cur <= d2:
            events[cur] = name
            cur += timedelta(days=1)
    else:
        events[_to_date(body, year)] = name


def load_json_events(path: str, events: dict) -> None:
    """从 JSON 文件读取节假日：数组 [{date,name},...] 或 {date:name}。"""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except OSError as exc:
        raise ValueError(f"无法读取 JSON 文件 {path}: {exc}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 解析失败 {path}: {exc}") from None
    if isinstance(data, dict):
        pairs = list(data.items())
    elif isinstance(data, list):
        pairs = []
        for i, item in enumerate(data):
            if not isinstance(item, dict) or "date" not in item:
                raise ValueError(f"JSON 第 {i} 项需要是含 date 字段的对象")
            pairs.append((item["date"], item.get("name")))
    else:
        raise ValueError("JSON 顶层需要是数组或对象")
    for key, name in pairs:
        try:
            d = date.fromisoformat(str(key).strip())
        except ValueError:
            raise ValueError(f"JSON 中无效日期: {key!r}") from None
        events[d] = str(name).strip() if name else DEFAULT_NAME


def ics_escape(text: str) -> str:
    """RFC 5545 TEXT 转义。"""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold_line(line: str) -> list:
    """按 RFC 5545 把超过 75 字节的行折叠为续行（续行以空格开头）。"""
    if len(line.encode("utf-8")) <= 75:
        return [line]
    lines, cur, cur_len = [], [], 0
    for ch in line:
        b = ch.encode("utf-8")
        if cur_len + len(b) > 75:
            lines.append("".join(cur))
            cur, cur_len = [" "], 1
        cur.append(ch)
        cur_len += len(b)
    if cur:
        lines.append("".join(cur))
    return lines


def build_ics(events: dict, cal_name: str) -> str:
    """生成 VCALENDAR 文本（全天事件，DTEND 为次日的排他边界）。"""
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_escape(cal_name)}",
    ]
    for d, name in sorted(events.items()):
        digest = hashlib.sha1(f"{d.isoformat()}|{name}".encode("utf-8")).hexdigest()[:16]
        try:
            nxt = d + timedelta(days=1)
        except OverflowError:
            raise ValueError(f"日期 {d} 位于支持范围末端，无法生成 DTEND") from None
        lines += [
            "BEGIN:VEVENT",
            f"UID:holiday-{digest}@tool-armory.local",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{nxt.strftime('%Y%m%d')}",
            f"SUMMARY:{ics_escape(name)}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    out = []
    for ln in lines:
        out.extend(fold_line(ln))
    return "\r\n".join(out) + "\r\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="把某年节假日列表生成为 .ics 日历文件（可导入主流日历应用）")
    parser.add_argument("year", nargs="?", type=int,
                        help="年份（使用 MM-DD 形式的日期时必填）")
    parser.add_argument("--day", action="append", default=[], metavar="SPEC",
                        help="节假日: MM-DD[:名称] / MM-DD..MM-DD[:名称] / YYYY-MM-DD[:名称]，可重复")
    parser.add_argument("--json", metavar="FILE",
                        help="从 JSON 文件读取节假日（数组或 {日期: 名称}）")
    parser.add_argument("--out", "-o", metavar="FILE",
                        help="输出文件（默认 holidays-<年份>.ics）")
    parser.add_argument("--name", help="日历名称 X-WR-CALNAME（默认 “<年份>年节假日”）")
    args = parser.parse_args(argv)

    if not args.day and not args.json:
        parser.error("请至少提供一个 --day 或 --json")

    def is_partial(t: str) -> bool:
        return len(t.strip().split("-")) == 2

    needs_year = False
    for spec in args.day:
        body = spec.partition(":")[0]
        if ".." in body:
            a, _, b = body.partition("..")
            needs_year = needs_year or is_partial(a) or is_partial(b)
        else:
            needs_year = needs_year or is_partial(body)
    if needs_year and args.year is None:
        parser.error("存在 MM-DD 形式的日期，请提供年份参数")

    events = {}
    try:
        for spec in args.day:
            add_day_spec(spec, args.year, events)
        if args.json:
            load_json_events(args.json, events)
    except ValueError as exc:
        parser.exit(2, f"错误: {exc}\n")

    if not events:
        parser.error("未解析到任何节假日日期")

    year_label = str(args.year) if args.year is not None else "custom"
    out_path = args.out or f"holidays-{year_label}.ics"
    cal_name = args.name or (f"{args.year}年节假日" if args.year is not None else "节假日")
    content = build_ics(events, cal_name)
    try:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            f.write(content)
    except OSError as exc:
        print(f"错误: 无法写入 {out_path}: {exc}", file=sys.stderr)
        return 2

    preview = "，".join(f"{d.strftime('%m-%d')} {events[d]}" for d in sorted(events)[:3])
    more = "…" if len(events) > 3 else ""
    print(f"已写入 {len(events)} 个全天事件 -> {out_path} ({len(content.encode('utf-8'))} 字节)")
    print(f"事件预览: {preview}{more}")
    return 0


if __name__ == "__main__":
    _setup_stdio()
    sys.exit(main())
