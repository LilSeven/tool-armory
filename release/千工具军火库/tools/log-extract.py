#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""log-extract — 日志切片提取。

按级别、时间范围、关键字组合过滤日志，把命中的行原样写到新文件或标准输出。
多个条件之间为"与"关系：级别列表内任一命中即可，多个 --keyword 需同时命中
(关键字默认忽略大小写，--cs 开启区分大小写)。
时间过滤生效时，无法解析时间戳的行会被排除并在 stderr 提示数量。

支持的时间戳格式 (按本地时间解析，忽略时区后缀):
  2024-06-01 10:00:01    2024-06-01T10:00:01    2024-06-01 10:00:01.123
  2024/06/01 10:00:01    10:00:01

用法:
  python log-extract.py <日志文件|-> [-o 输出文件] [--level INFO,ERROR]
                        [--keyword 文本 ...] [--since "2024-06-01 10:00:00"]
                        [--until "2024-06-01 11:00:00"] [--cs] [--encoding utf-8]

示例:
  python log-extract.py app.log -o errors.log --level ERROR,FATAL
  python log-extract.py app.log -o slice.log --since "2024-06-01 10:00:00" --until "2024-06-01 10:05:00"
  python log-extract.py app.log -o db_errors.log --level ERROR --keyword db
  cat app.log | python log-extract.py - --keyword timeout -o out.log
"""

import argparse
import datetime
import os
import re
import sys

KNOWN_LEVELS = ("TRACE", "DEBUG", "INFO", "NOTICE", "WARN", "ERROR", "FATAL")
LEVEL_RE = re.compile(
    r"\b(TRACE|DEBUG|INFO|NOTICE|WARNING|WARN|ERROR|ERR|FATAL|CRITICAL)\b")
LEVEL_RE_LOOSE = re.compile(LEVEL_RE.pattern, re.IGNORECASE)
LEVEL_SYNONYM = {"WARNING": "WARN", "ERR": "ERROR", "CRITICAL": "FATAL"}

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


def detect_level(line):
    m = LEVEL_RE.search(line)
    if m:
        return LEVEL_SYNONYM.get(m.group(1), m.group(1))
    m = LEVEL_RE_LOOSE.search(line)
    if m:
        return LEVEL_SYNONYM.get(m.group(1).upper(), m.group(1).upper())
    return None


def parse_arg_ts(text):
    """把 --since/--until 参数解析为 epoch 秒；要求带日期，否则返回 None。"""
    p = parse_ts(text)
    if p is None or p[1] != "full":
        return None
    return p[0]


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        description="按级别/时间范围/关键字组合条件提取日志子集")
    ap.add_argument("file", help="日志文件路径, 传 - 读标准输入")
    ap.add_argument("-o", "--output", help="输出文件路径 (默认写到标准输出)")
    ap.add_argument("-l", "--level",
                    help="要提取的级别, 逗号分隔, 如 INFO,ERROR")
    ap.add_argument("-k", "--keyword", action="append", default=[],
                    help="关键字 (可多次给出, 需同时命中; 默认忽略大小写)")
    ap.add_argument("--since", help="起始时间 (含), 如 \"2024-06-01 10:00:00\"")
    ap.add_argument("--until", help="结束时间 (含)")
    ap.add_argument("--cs", action="store_true", help="关键字区分大小写")
    ap.add_argument("--encoding", default="utf-8",
                    help="输入/输出文件编码 (默认 utf-8)")
    args = ap.parse_args(argv)

    levels = None
    if args.level:
        levels = set()
        for part in args.level.split(","):
            part = part.strip().upper()
            if not part:
                continue
            part = LEVEL_SYNONYM.get(part, part)
            if part not in KNOWN_LEVELS:
                print("错误: 未知级别 {!r}, 支持的级别: {}".format(
                    part, "/".join(KNOWN_LEVELS)), file=sys.stderr)
                return 2
            levels.add(part)

    since = until = None
    if args.since:
        since = parse_arg_ts(args.since)
        if since is None:
            print("错误: --since 无法解析为带日期的时间: {!r}".format(
                args.since), file=sys.stderr)
            return 2
    if args.until:
        until = parse_arg_ts(args.until)
        if until is None:
            print("错误: --until 无法解析为带日期的时间: {!r}".format(
                args.until), file=sys.stderr)
            return 2
    if since is not None and until is not None and since > until:
        print("错误: --since 晚于 --until", file=sys.stderr)
        return 2

    if args.output and args.file != "-":
        if os.path.abspath(args.output) == os.path.abspath(args.file):
            print("错误: 输出文件与输入文件相同, 会覆盖原始日志, 已拒绝",
                  file=sys.stderr)
            return 2

    if args.file == "-":
        if not sys.stdin.isatty():
            try:
                sys.stdin.reconfigure(encoding="utf-8",
                                      errors="surrogateescape")
            except Exception:
                pass
        fh, need_close = sys.stdin, False
    else:
        try:
            fh = open(args.file, "r", encoding=args.encoding,
                      errors="surrogateescape")
        except OSError as e:
            print("错误: 无法打开 {}: {}".format(args.file, e), file=sys.stderr)
            return 2
        need_close = True

    out = sys.stdout
    need_out_close = False
    if args.output:
        try:
            out = open(args.output, "w", encoding=args.encoding,
                       errors="surrogateescape", newline="")
        except OSError as e:
            print("错误: 无法写入 {}: {}".format(args.output, e),
                  file=sys.stderr)
            return 2
        need_out_close = True

    keywords = [(kw if args.cs else kw.lower()) for kw in args.keyword]
    total = kept = no_ts_skipped = 0
    time_filter = since is not None or until is not None
    try:
        for line in fh:
            total += 1
            if levels is not None:
                lv = detect_level(line)
                if lv is None or lv not in levels:
                    continue
            if time_filter:
                p = parse_ts(line)
                if p is None:
                    no_ts_skipped += 1
                    continue
                t = p[0]
                if since is not None and t < since:
                    continue
                if until is not None and t > until:
                    continue
            if keywords:
                hay = line if args.cs else line.lower()
                if any(kw not in hay for kw in keywords):
                    continue
            out.write(line)
            kept += 1
    finally:
        if need_close:
            fh.close()
        if need_out_close:
            out.close()

    dest = args.output if args.output else "标准输出"
    print("已扫描 {} 行, 命中 {} 行 -> 写入 {} (级别过滤: {}; 时间过滤: {}; "
          "关键字: {})".format(
              total, kept, dest,
              ",".join(sorted(levels)) if levels else "无",
              "开" if time_filter else "无",
              "、".join(args.keyword) if args.keyword else "无"),
          file=sys.stderr)
    if time_filter and no_ts_skipped:
        print("注: 有 {} 行因无法解析时间戳而被时间过滤排除".format(
            no_ts_skipped), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
