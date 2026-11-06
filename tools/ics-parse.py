#!/usr/bin/env python3
"""iCal 文件解析 —— 解析 .ics（iCalendar）文件，列出事件时间与摘要。

用法:
    python ics-parse.py <文件.ics> [--start YYYY-MM-DD] [--end YYYY-MM-DD]

示例命令:
    python ics-parse.py sample.ics
    python ics-parse.py sample.ics --start 2026-11-01 --end 2026-11-30

说明:
    标准库 calendar 模块本身不提供 iCalendar 解析器（icalendar 为第三方库），
    因此本工具按 RFC 5545 常用子集自行解析：支持续行折叠（续行以空格/制表符开头）、
    VEVENT 的 DTSTART/DTEND/DURATION/SUMMARY/LOCATION/RRULE，
    支持 VALUE=DATE 全天事件、UTC(Z) 与 TZID 时区标注（不做时区换算，按字面时间排序）；
    星期计算借助标准库 calendar 模块完成。
    全天事件的 DTEND 按非含端点处理：显示为实际最后一天。
    输出按事件开始时间排序；--start/--end 按开始日期过滤（含端点）。

仅用 Python 标准库；退出码：0 正常，1 文件/解析错误，2 参数错误。
"""

import argparse
import calendar
import datetime as dt
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

DURATION_RE = re.compile(
    r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def parse_date(text):
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"日期格式应为 YYYY-MM-DD，收到 {text!r}")


def split_content_line(line):
    """按 RFC 5545 拆分 contentline：NAME[;PARAM=VALUE...]:value（冒号须不在双引号内）。"""
    in_quote = False
    colon = -1
    for i, ch in enumerate(line):
        if ch == '"':
            in_quote = not in_quote
        elif ch == ":" and not in_quote:
            colon = i
            break
    if colon < 0:
        return None, None, None
    head, value = line[:colon], line[colon + 1:]
    pieces = head.split(";")
    name = pieces[0].strip().upper()
    params = {}
    for p in pieces[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.strip().upper()] = v.strip().strip('"')
    return name, params, value


def parse_dt_value(value, params):
    """解析 DATE 或 DATE-TIME。返回 (date/datetime, 是否全天, 时区标注或 None)。"""
    v = value.strip()
    declared = (params.get("VALUE") or "").upper()
    if declared == "DATE" or (declared != "DATE-TIME" and re.fullmatch(r"\d{8}", v)):
        return dt.datetime.strptime(v, "%Y%m%d").date(), True, None
    body = v[:-1] if v.endswith("Z") else v
    if re.fullmatch(r"\d{8}T\d{6}", body):
        tz = "UTC" if v.endswith("Z") else params.get("TZID")
        return dt.datetime.strptime(body, "%Y%m%dT%H%M%S"), False, tz
    return None, False, None


def parse_duration(value):
    m = DURATION_RE.fullmatch(value.strip())
    if not m:
        return None
    sign, w, d, h, mi, s = m.groups()
    td = dt.timedelta(weeks=int(w or 0), days=int(d or 0),
                      hours=int(h or 0), minutes=int(mi or 0), seconds=int(s or 0))
    return -td if sign == "-" else td


def unescape_text(value):
    return (value.replace("\\\\", "\x00")
                 .replace("\\n", " ").replace("\\N", " ")
                 .replace("\\,", ",").replace("\\;", ";")
                 .replace("\x00", "\\"))


def read_text(path):
    with open(path, "rb") as fh:
        data = fh.read()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_ics(text):
    lines = []
    for raw in text.splitlines():
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)

    events = []
    stack = []
    cur = None
    for line in lines:
        name, params, value = split_content_line(line)
        if name is None:
            continue
        if name == "BEGIN":
            comp = value.strip().upper()
            stack.append(comp)
            if comp == "VEVENT" and stack.count("VEVENT") == 1:
                cur = {"summary": "(无摘要)", "location": None, "rrule": False,
                       "start": None, "end": None, "duration": None}
        elif name == "END":
            comp = value.strip().upper()
            if stack and stack[-1] == comp:
                stack.pop()
            if comp == "VEVENT" and cur is not None:
                events.append(cur)
                cur = None
        elif cur is not None and stack and stack[-1] == "VEVENT":
            if name == "DTSTART":
                cur["start"] = parse_dt_value(value, params)
            elif name == "DTEND":
                cur["end"] = parse_dt_value(value, params)
            elif name == "DURATION":
                cur["duration"] = parse_duration(value)
            elif name == "SUMMARY":
                cur["summary"] = unescape_text(value.strip()) or "(无摘要)"
            elif name == "LOCATION":
                cur["location"] = unescape_text(value.strip())
            elif name == "RRULE":
                cur["rrule"] = True
    return events


def sort_key(ev):
    if ev["start"] is None:
        return (1, dt.datetime(1, 1, 1), 0)
    obj, is_date, _tz = ev["start"]
    key = obj if isinstance(obj, dt.datetime) else dt.datetime.combine(obj, dt.time.min)
    return (0, key, 0 if is_date else 1)


def start_date(parsed):
    obj, is_date, _tz = parsed
    return obj if is_date else obj.date()


def fmt_start(obj, is_date, tz):
    if is_date:
        w = calendar.weekday(obj.year, obj.month, obj.day)
        return f"{obj.isoformat()}（全天·{WEEK[w]}）"
    s = obj.strftime("%Y-%m-%d %H:%M")
    if tz:
        s += f" [{tz}]"
    return s


def fmt_end(obj, is_date, tz):
    if is_date:
        return (obj - dt.timedelta(days=1)).isoformat()
    s = obj.strftime("%Y-%m-%d %H:%M")
    if tz:
        s += f" [{tz}]"
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="解析 .ics（iCalendar）文件，列出事件时间与摘要。")
    ap.add_argument("file", help=".ics 文件路径")
    ap.add_argument("--start", type=parse_date, default=None,
                    help="仅显示开始日期不早于该日的事件")
    ap.add_argument("--end", type=parse_date, default=None,
                    help="仅显示开始日期不晚于该日的事件")
    args = ap.parse_args(argv)

    try:
        text = read_text(args.file)
    except OSError as exc:
        print(f"错误：无法读取文件 {args.file}：{exc}", file=sys.stderr)
        return 1

    events = parse_ics(text)
    events.sort(key=sort_key)
    if args.start is not None:
        events = [e for e in events if e["start"] and start_date(e["start"]) >= args.start]
    if args.end is not None:
        events = [e for e in events if e["start"] and start_date(e["start"]) <= args.end]

    print(f"文件：{args.file}")
    if not events:
        print("未解析到任何 VEVENT 事件。")
        return 0
    print(f"共解析到 {len(events)} 个事件（VEVENT）：")
    for i, ev in enumerate(events, 1):
        if ev["start"]:
            obj, is_date, tz = ev["start"]
            line = f"  {i}. {fmt_start(obj, is_date, tz)}"
            end_str = None
            if ev["end"]:
                end_obj, end_is_date, end_tz = ev["end"]
                if not (is_date and end_is_date
                        and end_obj - dt.timedelta(days=1) == obj):
                    end_str = fmt_end(end_obj, end_is_date, end_tz)
            elif ev["duration"] is not None:
                end_obj = obj + ev["duration"]
                if not (is_date and end_obj - dt.timedelta(days=1) == obj):
                    end_str = fmt_end(end_obj, is_date, tz)
            if end_str:
                line += f" ~ {end_str}"
        else:
            line = f"  {i}. （无开始时间）"
        title = ev["summary"] + ("（重复）" if ev["rrule"] else "")
        if ev["location"]:
            title += f" @{ev['location']}"
        print(f"{line}  {title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
