#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""iCal 事件生成 —— 从命令行参数生成含 VEVENT 的 .ics 日历文件。

用途:
    将命令行参数组装成符合 RFC 5545 的 VCALENDAR/VEVENT 结构并写出 .ics
    文件 (不指定 -o 时打印到标准输出)。支持定时事件与全天事件, 自动生成
    UID 与 DTSTAMP, 对 SUMMARY/LOCATION/DESCRIPTION 做 TEXT 转义, 超长行
    按 RFC 折行 (每行 <= 75 八位组, 续行以空格开头)。

示例:
    python ics-generate.py -s "团队周会" --dtstart 2026-11-05T10:00:00 --dtend 2026-11-05T11:00:00 -o meeting.ics
    python ics-generate.py -s "全天活动" --date 2026-11-06 --days 2 -o allday.ics
    python ics-generate.py -s "演示" --dtstart 20261105T093000 --duration 90m --print

仅使用 Python 标准库 (3.8+)。
"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone

PRODID = "-//tool-armory//ics-generate 1.0//CN"

_DT_FORMATS = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
               "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
               "%Y%m%dT%H%M%S", "%Y%m%dT%H%M",
               "%Y-%m-%d", "%Y%m%d")
_DATE_ONLY = {"%Y-%m-%d", "%Y%m%d"}


def _setup_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_dt(text: str):
    """解析时间参数, 返回 (datetime, 是否为纯日期)。"""
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt), fmt in _DATE_ONLY
        except ValueError:
            continue
    raise SystemExit(f"错误: 无法识别的时间 {text!r} "
                     "(示例: 2026-11-05T10:00:00 / 20261105T093000 / 2026-11-05)")


def parse_duration(text: str) -> timedelta:
    m = re.fullmatch(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?",
                     text.strip().lower())
    if not m or not any(m.groups()):
        raise SystemExit(f"错误: 无法识别的时长 {text!r} (示例: 90m / 2h / 1h30m / 2d)")
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return timedelta(days=d, hours=h, minutes=mi, seconds=s)


def escape_text(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;")
                .replace(",", "\\,")
                .replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n"))


def fold(line: str) -> list:
    """RFC 5545 折行: 单行不超过 75 八位组, 续行以空格开头。"""
    if len(line.encode("utf-8")) <= 75:
        return [line]
    chunks, cur, cur_len, limit = [], [], 0, 75
    for ch in line:
        w = len(ch.encode("utf-8"))
        if cur_len + w > limit:
            chunks.append("".join(cur))
            cur, cur_len, limit = [], 0, 74  # 续行前导空格占 1 字节
        cur.append(ch)
        cur_len += w
    chunks.append("".join(cur))
    return [chunks[0]] + [" " + c for c in chunks[1:]]


def build_lines(args) -> list:
    if args.date and args.dtstart:
        raise SystemExit("错误: --date 与 --dtstart 不能同时使用")
    if not args.date and not args.dtstart:
        raise SystemExit("错误: 需要 --dtstart 或 --date")

    if args.date:
        start, date_only = parse_dt(args.date)
        if not date_only:
            raise SystemExit("错误: --date 需要纯日期, 例如 2026-11-06")
    else:
        start, date_only = parse_dt(args.dtstart)
        if date_only:
            raise SystemExit("错误: --dtstart 需要带时间; 全天事件请改用 --date")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}",
             "CALSCALE:GREGORIAN"]
    if args.calname:
        lines.append(f"X-WR-CALNAME:{escape_text(args.calname)}")

    uid = args.uid or f"{uuid.uuid4()}@tool-armory"
    lines.append("BEGIN:VEVENT")
    lines.append(f"UID:{uid}")
    lines.append("DTSTAMP:" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))

    if date_only:
        days = max(1, args.days)
        lines.append(f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}")
        # RFC 5545: 全天事件 DTEND 为排他端点
        lines.append("DTEND;VALUE=DATE:" + (start + timedelta(days=days)).strftime("%Y%m%d"))
    else:
        lines.append("DTSTART:" + start.strftime("%Y%m%dT%H%M%S"))
        if args.dtend and args.duration:
            raise SystemExit("错误: --dtend 与 --duration 只能提供一个")
        if args.dtend:
            end, end_date_only = parse_dt(args.dtend)
            if end_date_only:
                raise SystemExit("错误: 定时事件需要带时间的 --dtend")
            lines.append("DTEND:" + end.strftime("%Y%m%dT%H%M%S"))
        elif args.duration:
            lines.append("DTEND:" + (start + parse_duration(args.duration)).strftime("%Y%m%dT%H%M%S"))

    lines.append(f"SUMMARY:{escape_text(args.summary)}")
    if args.location:
        lines.append(f"LOCATION:{escape_text(args.location)}")
    if args.description:
        lines.append(f"DESCRIPTION:{escape_text(args.description)}")
    lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return lines


def main(argv=None) -> int:
    _setup_streams()
    p = argparse.ArgumentParser(
        prog="ics-generate",
        description="从命令行参数生成含 VEVENT 的 .ics 日历文件 (RFC 5545)")
    p.add_argument("-s", "--summary", required=True, help="事件标题 (SUMMARY)")
    p.add_argument("--dtstart", help="开始时间, 如 2026-11-05T10:00:00 或 20261105T093000")
    p.add_argument("--dtend", help="结束时间 (与 --duration 二选一)")
    p.add_argument("--duration", help="持续时长, 如 90m / 2h / 1h30m / 2d")
    p.add_argument("--date", help="全天事件日期, 如 2026-11-06 (与 --dtstart 互斥)")
    p.add_argument("--days", type=int, default=1, help="全天事件持续天数 (默认 1)")
    p.add_argument("--location", help="地点 (LOCATION)")
    p.add_argument("--description", help="描述 (DESCRIPTION)")
    p.add_argument("--uid", help="事件 UID, 缺省自动生成")
    p.add_argument("--calname", help="日历名称 (X-WR-CALNAME)")
    p.add_argument("-o", "--output", help="输出 .ics 路径, 缺省打印到标准输出")
    p.add_argument("--print", action="store_true", help="打印内容到标准输出 (忽略 -o)")
    args = p.parse_args(argv)

    lines = build_lines(args)
    content = "\r\n".join(l for line in lines for l in fold(line)) + "\r\n"

    if args.output and not args.print:
        try:
            with open(args.output, "w", encoding="utf-8", newline="") as fh:
                fh.write(content)
        except OSError as exc:
            print(f"错误: 写入 {args.output} 失败: {exc}", file=sys.stderr)
            return 1
        print(f"已写入 {args.output} ({len(lines)} 行属性)")
    else:
        sys.stdout.write(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
