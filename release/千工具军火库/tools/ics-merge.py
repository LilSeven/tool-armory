#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日历文件合并 —— 合并多个 .ics 文件并按 UID 去重输出单一日历。

用途:
    读取多个 iCalendar (.ics) 文件, 抽取其中的 VTIMEZONE 与 VEVENT, 按 UID
    去重 (同一 UID 先出现者保留, 后出现者跳过; 无 UID 的事件按内容 SHA1
    生成稳定 UID) 合并为单一 VCALENDAR 输出, 并沿用第一个输入文件的
    X-WR-CALNAME (可用 --calname 覆盖)。输入支持 RFC 5545 折行, 输出同样
    按 75 八位组折行。统计信息写往 stderr, 日历内容写往文件或 stdout。

示例:
    python ics-merge.py a.ics b.ics -o merged.ics
    python ics-merge.py a.ics b.ics c.ics --calname "合并日历" --print

仅使用 Python 标准库 (3.8+)。
"""

from __future__ import annotations

import argparse
import hashlib
import sys

PRODID = "-//tool-armory//ics-merge 1.0//CN"


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


def escape_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")


def fold(line: str) -> list:
    """RFC 5545 折行: 单行不超过 75 八位组, 续行以空格开头。"""
    if len(line.encode("utf-8")) <= 75:
        return [line]
    chunks, cur, cur_len, limit = [], [], 0, 75
    for ch in line:
        w = len(ch.encode("utf-8"))
        if cur_len + w > limit:
            chunks.append("".join(cur))
            cur, cur_len, limit = [], 0, 74
        cur.append(ch)
        cur_len += w
    chunks.append("".join(cur))
    return [chunks[0]] + [" " + c for c in chunks[1:]]


def split_blocks(lines: list):
    """返回 (events, timezones, cal_props): 块内为原始行列表, 块外为属性行。"""
    events, timezones, cal_props = [], [], []
    cur, kind = None, None
    for line in lines:
        parsed = parse_line(line)
        name = parsed[0] if parsed else ""
        value = parsed[2].strip().upper() if parsed else ""
        if cur is None:
            if name == "BEGIN" and value in ("VEVENT", "VTIMEZONE"):
                kind = value
                cur = [line]
            else:
                cal_props.append(line)
        else:
            cur.append(line)
            if name == "END" and value == kind:
                (events if kind == "VEVENT" else timezones).append(cur)
                cur, kind = None, None
    return events, timezones, cal_props


def event_uid(ev_lines: list):
    for line in ev_lines:
        parsed = parse_line(line)
        if parsed and parsed[0] == "UID" and parsed[2].strip():
            return parsed[2].strip(), False
    digest = hashlib.sha1("\n".join(ev_lines).encode("utf-8", "replace")).hexdigest()[:12]
    return f"merged-{digest}@local", True


def tzid_of(tz_lines: list):
    for line in tz_lines:
        parsed = parse_line(line)
        if parsed and parsed[0] == "TZID" and parsed[2].strip():
            return parsed[2].strip()
    return None


def main(argv=None) -> int:
    _setup_streams()
    p = argparse.ArgumentParser(
        prog="ics-merge",
        description="合并多个 .ics 文件并按 UID 去重, 输出单一日历")
    p.add_argument("inputs", nargs="+", help="输入的 .ics 文件 (至少一个)")
    p.add_argument("-o", "--output", help="输出 .ics 路径, 缺省打印到标准输出")
    p.add_argument("--calname", help="输出日历名称 (X-WR-CALNAME), 缺省沿用第一个输入文件的值")
    p.add_argument("--print", action="store_true", help="打印内容到标准输出 (忽略 -o)")
    args = p.parse_args(argv)

    all_events = []
    tz_map, tz_order = {}, []
    calname = None
    per_file = []

    for idx, path in enumerate(args.inputs):
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            print(f"错误: 读取 {path} 失败: {exc}", file=sys.stderr)
            return 1
        events, timezones, cal_props = split_blocks(unfold(text))
        per_file.append(f"{path} ({len(events)} 事件)")
        for tz in timezones:
            tzid = tzid_of(tz) or f"tz-{len(tz_map)}"
            if tzid not in tz_map:
                tz_map[tzid] = tz
                tz_order.append(tzid)
        if idx == 0:
            for line in cal_props:
                parsed = parse_line(line)
                if parsed and parsed[0] == "X-WR-CALNAME" and calname is None:
                    calname = parsed[2].strip()
        for ev in events:
            uid, generated = event_uid(ev)
            if generated:
                # 原 UID 行不存在, 把指纹 UID 注入到输出事件里 (RFC 5545 要求 UID)
                ev = ev[:1] + [f"UID:{uid}"] + ev[1:]
            all_events.append((uid, generated, idx, ev))

    merged, dups = [], []
    seen = {}
    for uid, generated, idx, ev in all_events:
        if uid in seen:
            dups.append((uid, seen[uid], idx))
        else:
            seen[uid] = idx
            merged.append((uid, ev))

    out = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}",
           "CALSCALE:GREGORIAN"]
    final_calname = escape_text(args.calname) if args.calname is not None else calname
    if final_calname:
        out.append(f"X-WR-CALNAME:{final_calname}")
    for tzid in tz_order:
        out.extend(tz_map[tzid])
    for _, ev in merged:
        out.extend(ev)
    out.append("END:VCALENDAR")

    gen = sum(1 for _, g, _, _ in all_events if g)
    print(f"输入 {len(args.inputs)} 个文件: {', '.join(per_file)}", file=sys.stderr)
    print(f"事件共 {len(all_events)} 个, 按 UID 去重后 {len(merged)} 个"
          f" (跳过重复 {len(dups)} 个; {gen} 个原无 UID, 已按内容指纹补 UID)",
          file=sys.stderr)
    for uid, i, j in dups:
        print(f"  重复: UID {uid} (保留 {args.inputs[i]}, 跳过 {args.inputs[j]})",
              file=sys.stderr)
    print(f"时区定义 (VTIMEZONE) {len(tz_order)} 个", file=sys.stderr)

    content = "\r\n".join(l for line in out for l in fold(line)) + "\r\n"
    if args.output and not args.print:
        try:
            with open(args.output, "w", encoding="utf-8", newline="") as fh:
                fh.write(content)
        except OSError as exc:
            print(f"错误: 写入 {args.output} 失败: {exc}", file=sys.stderr)
            return 1
        print(f"输出: {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
