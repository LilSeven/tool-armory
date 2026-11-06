#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""log-timeline-buckets — 日志时间线。

按时间桶聚合日志条数，用 ASCII 柱状图展示日志量随时间的变化，
便于快速定位日志高峰、低谷与静默时段。空桶 (该时段无日志) 也会显示。

支持的时间戳格式 (按本地时间解析，忽略时区后缀):
  2024-06-01 10:00:01    2024-06-01T10:00:01    2024-06-01 10:00:01.123
  2024/06/01 10:00:01    10:00:01               10:00:01,123 (仅时间, 自动跨天)

用法:
  python log-timeline-buckets.py <日志文件|-> [-b 桶大小] [-w 宽度]

示例:
  python log-timeline-buckets.py app.log --bucket 1m
  python log-timeline-buckets.py app.log --bucket auto --width 60
  tail -n 2000 app.log | python log-timeline-buckets.py -
"""

import argparse
import datetime
import math
import re
import sys
from collections import defaultdict

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


def fmt_bucket(v):
    if v >= 86400 and v % 86400 == 0:
        return "{:g}d".format(v / 86400)
    if v >= 60 and v % 60 == 0:
        return "{:g}m".format(v / 60)
    return "{:g}s".format(v)


def bucket_arg(text):
    if text.strip().lower() == "auto":
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([smhd]?)", text.strip(),
                     re.IGNORECASE)
    if m is None:
        raise argparse.ArgumentTypeError(
            "桶大小格式应为 <数字><s|m|h|d> (如 10s/5m/1h/1d) 或 auto")
    mult = {"": 1.0, "s": 1.0, "m": 60.0, "h": 3600.0,
            "d": 86400.0}[m.group(2).lower()]
    val = float(m.group(1)) * mult
    if val <= 0:
        raise argparse.ArgumentTypeError("桶大小必须大于 0")
    return val


_NICE_STEPS = (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800,
               3600, 7200, 14400, 21600, 43200, 86400)


def choose_auto_bucket(span):
    """根据时间跨度自动选一个"约 50 个桶"的整洁桶大小。"""
    if span <= 0:
        return 1.0
    target = span / 50.0
    for step in _NICE_STEPS:
        if step >= target:
            return float(step)
    return float((int(target // 86400) + 1) * 86400)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        description="按时间桶聚合日志条数并绘制 ASCII 柱状图")
    ap.add_argument("file", help="日志文件路径, 传 - 读标准输入")
    ap.add_argument("-b", "--bucket", type=bucket_arg, default=None,
                    help="时间桶大小, 如 10s/5m/1h/1d, 默认 auto (自动选择)")
    ap.add_argument("-w", "--width", type=int, default=50,
                    help="柱子最大宽度, 单位字符 (默认 50)")
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

    stamps = []
    total = 0
    try:
        for line in fh:
            total += 1
            p = parse_ts(line)
            if p is not None:
                stamps.append(p[0])
    finally:
        if need_close:
            fh.close()

    if not stamps:
        print("未解析到任何时间戳 (共 {} 行)。支持的时间格式见 --help。".format(
            total), file=sys.stderr)
        return 0

    span = max(stamps) - min(stamps)
    bucket = args.bucket if args.bucket is not None else choose_auto_bucket(span)
    counts = defaultdict(int)
    for t in stamps:
        counts[int(math.floor(t / bucket))] += 1

    width = max(10, min(200, args.width))
    b_lo, b_hi = min(counts), max(counts)
    max_count = max(counts.values())
    if bucket >= 86400:
        label_fmt = "%Y-%m-%d"
    elif span >= 86400:
        label_fmt = "%m-%d %H:%M"
    elif bucket >= 60:
        label_fmt = "%H:%M"
    else:
        label_fmt = "%H:%M:%S"

    print("时间线: 桶={}  范围: {} ~ {}  桶数={}  解析 {}/{} 行".format(
        fmt_bucket(bucket),
        fmt_ts(min(stamps)).strftime("%Y-%m-%d %H:%M:%S"),
        fmt_ts(max(stamps)).strftime("%Y-%m-%d %H:%M:%S"),
        b_hi - b_lo + 1, len(stamps), total))
    for i in range(b_lo, b_hi + 1):
        c = counts.get(i, 0)
        bar = "#" * (max(1, int(round(c * width / max_count))) if c else 0)
        print("{} | {:<{w}} {:>8}".format(
            fmt_ts(i * bucket).strftime(label_fmt), bar, c, w=width))
    return 0


if __name__ == "__main__":
    sys.exit(main())
