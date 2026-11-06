#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""log-time-range — 日志时间跨度。

解析日志首尾时间戳，报告总时间跨度，并按持续时间列出中间"没有任何日志"
的空档，用于快速发现服务停摆、静默或日志丢失的时段。
假定日志大致按时间排序。

支持的时间戳格式 (按本地时间解析，忽略时区后缀):
  2024-06-01 10:00:01    2024-06-01T10:00:01    2024/06/01 10:00:01
  10:00:01 (仅时间, 自动处理跨天)

用法:
  python log-time-range.py <日志文件|-> [--min-gap 60s] [--top 10] [--json]

示例:
  python log-time-range.py app.log
  python log-time-range.py app.log --min-gap 5m --top 20
  tail -n 5000 app.log | python log-time-range.py - --min-gap 30s
"""

import argparse
import datetime
import json
import math
import re
import sys

_EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
_RE_ISO = re.compile(
    r"\b(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:[.,](\d{1,6}))?")
_RE_SLASH = re.compile(
    r"\b(\d{4})/(\d{2})/(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:[.,](\d{1,6}))?")
_RE_TIME = re.compile(r"(?<!\d)(\d{2}):(\d{2}):(\d{2})(?:[.,](\d{1,6}))?(?!\d)")

# 本地时区当前 UTC 偏移 (秒), 用于 Windows mktime/astimezone 无法处理的负时间戳
_UTC_OFFSET_S = (datetime.datetime.now(datetime.timezone.utc)
                 .astimezone().utcoffset().total_seconds())


def _safe_timestamp(dt):
    """naive 本地时间 -> epoch 秒。

    Windows 的 mktime 对负值 (如 UTC+8 下 1970-01-01 00:00:01 本地时间)
    会抛 OSError, 失败时改用本地 UTC 偏移做纯算术换算。
    """
    try:
        return dt.timestamp()
    except (OSError, OverflowError, ValueError):
        return (dt.replace(tzinfo=datetime.timezone.utc).timestamp()
                - _UTC_OFFSET_S)


def parse_ts(line):
    """从一行文本解析时间戳，返回 (epoch 秒, 类型) 或 None。

    类型: "full"=带日期, "time"=仅时间 (以 1970-01-01 为基准)。
    """
    m = _RE_ISO.search(line)
    if m is None:
        m = _RE_SLASH.search(line)
    if m is not None:
        y, mo, d, h, mi, s = (int(m.group(i)) for i in range(1, 7))
        try:
            dt = datetime.datetime(y, mo, d, h, mi, s)
        except ValueError:
            return None
        if m.group(7):
            dt += datetime.timedelta(seconds=float("0." + m.group(7)))
        return _safe_timestamp(dt), "full"
    m = _RE_TIME.search(line)
    if m is not None:
        h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if h > 23 or mi > 59 or s > 59:
            return None
        dt = datetime.datetime(1970, 1, 1, h, mi, s)
        if m.group(4):
            dt += datetime.timedelta(seconds=float("0." + m.group(4)))
        return _safe_timestamp(dt), "time"
    return None


def fmt_ts(t):
    """epoch 秒 -> 本地墙钟 naive datetime (纯算术, 兼容负时间戳)。"""
    return _EPOCH + datetime.timedelta(seconds=t + _UTC_OFFSET_S)


def human_dur(sec):
    """把秒数格式化为人类可读时长, 如 34m57s / 1h02m03s / 45.5s。"""
    sec = float(sec)
    if sec < 1.0:
        return "{:.0f}ms".format(sec * 1000)
    if sec < 60.0:
        return "{:g}s".format(sec)
    total = int(round(sec))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return "{}h{:02d}m{:02d}s".format(h, m, s)
    return "{}m{:02d}s".format(m, s)


def duration_arg(text):
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([smhd]?)", text.strip(),
                     re.IGNORECASE)
    if m is None:
        raise argparse.ArgumentTypeError(
            "时长格式应为 <数字><s|m|h|d>, 如 30s/5m/1h")
    mult = {"": 1.0, "s": 1.0, "m": 60.0, "h": 3600.0,
            "d": 86400.0}[m.group(2).lower()]
    val = float(m.group(1)) * mult
    if val <= 0:
        raise argparse.ArgumentTypeError("时长必须大于 0")
    return val


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        description="解析日志首尾时间戳, 报告时间跨度及中间的无日志空档")
    ap.add_argument("file", help="日志文件路径, 传 - 读标准输入")
    ap.add_argument("--min-gap", type=duration_arg, default=60.0,
                    help="判定为空档的最小时长 (默认 60s)")
    ap.add_argument("--top", type=int, default=10,
                    help="最多显示前 N 个最长空档 (默认 10, 0=全部)")
    ap.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = ap.parse_args(argv)

    if args.file == "-":
        if not sys.stdin.isatty():
            try:
                sys.stdin.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        fh, need_close = sys.stdin, False
    else:
        try:
            fh = open(args.file, "r", encoding="utf-8", errors="replace")
        except OSError as e:
            print("错误: 无法打开 {}: {}".format(args.file, e), file=sys.stderr)
            return 2
        need_close = True

    total = 0
    stamps = []  # (行号, epoch 秒)
    shift = 0.0  # 仅时间格式跨天时的天数偏移
    prev = None
    try:
        for line in fh:
            total += 1
            p = parse_ts(line)
            if p is None:
                continue
            t, kind = p
            if kind == "time" and prev is not None and t + shift < prev - 1.0:
                shift += 86400.0 * math.ceil((prev - (t + shift)) / 86400.0)
            t += shift
            prev = t
            stamps.append((total, t))
    finally:
        if need_close:
            fh.close()

    if not stamps:
        print("未解析到任何时间戳 (共 {} 行)。支持的时间格式见 --help。".format(
            total), file=sys.stderr)
        return 0

    first_no, first_ts = stamps[0]
    last_no, last_ts = stamps[-1]
    span = last_ts - first_ts
    gaps = []
    for (l1, t1), (l2, t2) in zip(stamps, stamps[1:]):
        d = t2 - t1
        if d > args.min_gap:
            gaps.append({"seconds": d, "from_line": l1, "to_line": l2,
                         "from": t1, "to": t2})
    gaps.sort(key=lambda g: -g["seconds"])
    shown = gaps[:args.top] if args.top > 0 else gaps

    if args.json:
        data = {
            "file": args.file,
            "total_lines": total,
            "parsed_lines": len(stamps),
            "first": {"line": first_no, "ts": fmt_ts(first_ts).isoformat()},
            "last": {"line": last_no, "ts": fmt_ts(last_ts).isoformat()},
            "span_seconds": round(span, 3),
            "min_gap_seconds": args.min_gap,
            "gap_count": len(gaps),
            "gaps": [
                {"from_line": g["from_line"], "to_line": g["to_line"],
                 "from": fmt_ts(g["from"]).isoformat(),
                 "to": fmt_ts(g["to"]).isoformat(),
                 "seconds": round(g["seconds"], 3)}
                for g in shown
            ],
        }
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    tfmt = "%Y-%m-%d %H:%M:%S"
    span_s = int(span) if abs(span - round(span)) < 1e-9 else round(span, 3)
    print("日志时间跨度: {}".format(args.file))
    print("  起始  {}  (第 {} 行)".format(
        fmt_ts(first_ts).strftime(tfmt), first_no))
    print("  结束  {}  (第 {} 行)".format(
        fmt_ts(last_ts).strftime(tfmt), last_no))
    print("  跨度  {} ({} 秒)".format(human_dur(span), span_s))
    print("  时间戳解析: {}/{} 行".format(len(stamps), total))
    total_gap = sum(g["seconds"] for g in gaps)
    print("  空档 (> {}): 共 {} 处, 累计 {}".format(
        human_dur(args.min_gap), len(gaps), human_dur(total_gap)))
    for i, g in enumerate(shown, 1):
        print("    {}. {}  第 {} 行 -> 第 {} 行  {} -> {}".format(
            i, human_dur(g["seconds"]), g["from_line"], g["to_line"],
            fmt_ts(g["from"]).strftime(tfmt), fmt_ts(g["to"]).strftime(tfmt)))
    if args.top > 0 and len(gaps) > len(shown):
        print("    ... 其余 {} 个更短的空档未显示 (--top 可调)".format(
            len(gaps) - len(shown)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
