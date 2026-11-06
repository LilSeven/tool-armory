#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""时间点二分定位 — 利用日志时间戳的有序性, 二分查找某时刻在(大)日志文件中的位置。

对"时间戳单调不减"的日志文件, 只需 O(log 文件字节) 次探测即可定位目标时刻所在行,
无需整文件扫描。输出命中行号(1 起)、字节偏移与该行内容; 可用 -A 继续打印后续行。

用法:
  python log-time-locate.py app.log "2024-06-01 12:00:00"
  python log-time-locate.py app.log "2024-06-01T12:00:00.123" -A 50
  python log-time-locate.py app.log 1717245030                # 也支持 epoch 秒
  python log-time-locate.py app.log "2024-06-01 12:00:00" --before   # 目标之前最后一行
  python log-time-locate.py messy.log "2024-06-01 12:00:00" --linear # 乱序日志线性兜底

可识别的行内时间戳(取每行第一处命中):
  "2024-06-01 12:00:00(.f)" / "2024-06-01T12:00:00(.f)" / "2024/06/01 12:00:00"
  10 位 epoch 秒 / 13 位 epoch 毫秒 / 紧凑 14 位 "20240601120000"
目标时刻支持: "YYYY-MM-DD[ HH:MM[:SS[.f]]]"、"YYYY/MM/DD HH:MM:SS"、9~13 位 epoch。
二分模式假设时间戳非减; 探测行解析不出时间戳时结果可能偏移(stderr 会告警),
乱序或无时间戳的日志请用 --linear 逐行扫描。
退出码: 0 成功(含"未命中"的提示); 2 参数或文件错误。
"""

import argparse
import os
import re
import sys
from datetime import datetime, timedelta

EPOCH = datetime(1970, 1, 1)

TARGET_FORMATS = [
    "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
    "%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d", "%Y%m%d%H%M%S",
]

# (编译后的正则, 类型); 顺序即尝试顺序, 取每行第一处命中
LINE_TS_PATTERNS = [
    (re.compile(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?)"), "iso"),
    (re.compile(r"(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?)"), "slash"),
    (re.compile(r"(?<![\d.])(1\d{12})(?![\d.])"), "epoch_ms"),
    (re.compile(r"(?<![\d.])(1\d{9})(?![\d.])"), "epoch_s"),
    (re.compile(r"(?<![\d.])((?:19|20)\d{12})(?![\d.])"), "compact"),
]


def _force_utf8():
    """Windows 控制台/管道下强制 UTF-8。"""
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def parse_target(text):
    """目标时刻字符串 -> 相对 1970-01-01 的秒数(float), 不涉时区。"""
    t = text.strip().strip('"').strip("'")
    if re.fullmatch(r"\d{9,13}", t):
        v = int(t)
        return v / 1000.0 if len(t) >= 12 else float(v)
    t2 = t.replace(",", ".")
    for fmt in TARGET_FORMATS:
        try:
            return (datetime.strptime(t2, fmt) - EPOCH).total_seconds()
        except ValueError:
            pass
    raise ValueError("无法识别的时刻 %r (支持 YYYY-MM-DD[ HH:MM[:SS[.f]]] 或 9~13 位 epoch)" % text)


def fmt_ts(epoch):
    return (EPOCH + timedelta(seconds=epoch)).strftime("%Y-%m-%d %H:%M:%S")


def extract_ts(line):
    """从一行文本中提取时间戳, 返回 (epoch 秒, 命中原文) 或 None。"""
    s = line[:600]  # 时间戳通常在行首附近, 限制扫描范围提速
    for rx, kind in LINE_TS_PATTERNS:
        m = rx.search(s)
        if not m:
            continue
        text = m.group(1)
        try:
            if kind == "iso":
                dt = datetime.fromisoformat(text.replace(",", "."))
            elif kind == "slash":
                dt = datetime.fromisoformat(text.replace("/", "-").replace(",", "."))
            elif kind == "epoch_ms":
                return int(text) / 1000.0, text
            elif kind == "epoch_s":
                return float(text), text
            else:  # compact
                dt = datetime.strptime(text, "%Y%m%d%H%M%S")
        except ValueError:
            continue
        return (dt - EPOCH).total_seconds(), text
    return None


def line_start_containing(f, off):
    """返回包含字节偏移 off 的那一行的行首(要求 0 <= off < 文件大小)。"""
    if off <= 0:
        return 0
    f.seek(off - 1)
    if f.read(1) == b"\n":
        return off  # off 恰为行首
    # off 在行中: 向后找 off 之前最近的换行
    return line_start_prev(f, off)


def read_line_at(f, start):
    f.seek(start)
    return f.readline()


def line_start_prev(f, start):
    """start 是某行行首(或文件尾), 返回它之前那一行的行首; start<=0 返回 None。"""
    if start <= 0:
        return None
    k = 4096
    while True:
        begin = max(0, start - k)
        f.seek(begin)
        window = f.read(start - begin)
        # 排除末字节(它是上一行的换行符), 找再往前的最后一个换行
        j = window.rfind(b"\n", 0, max(0, len(window) - 1))
        if j >= 0:
            return begin + j + 1
        if begin == 0:
            return 0
        k *= 16


def count_lines_before(path, offset):
    """offset 之前有多少个换行 -> 若 offset 是行首, 该行行号 = 返回值。"""
    n = 1
    done = 0
    with open(path, "rb") as f:
        while done < offset:
            chunk = f.read(min(1 << 20, offset - done))
            if not chunk:
                break
            n += chunk.count(b"\n")
            done += len(chunk)
    return n


def bisect_locate(path, target, stats):
    """二分查找第一个 '时间戳 >= target' 的行首偏移。"""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        lo, hi = 0, size
        while lo < hi:
            mid = (lo + hi) // 2
            stats["probes"] += 1
            start = line_start_containing(f, mid)
            ts = None
            probe = start
            probe_end = start
            for _ in range(3):  # 该行及向后 2 行内找时间戳
                if probe >= size:
                    break
                raw = read_line_at(f, probe)
                probe_end = probe + len(raw)
                got = extract_ts(raw.decode("utf-8", "replace"))
                if got is not None:
                    ts = got
                    break
                probe = probe_end
            if ts is None:
                stats["blind"] += 1
                hi = start
            elif ts[0] >= target:
                hi = start
            else:
                lo = probe_end
        return lo


def linear_locate(path, target, before, stats):
    """线性扫描兜底。返回 (status, start, line_no, raw),
    status: hit / exhausted(所有行都早于目标) / before_empty(没有更早的行)。"""
    prev = None      # 最近一个 ts < target 的行
    last_seen = None # 最近一个能解析出时间戳的行
    offset = 0
    line_no = 0
    with open(path, "rb") as f:
        for raw in f:
            line_no += 1
            stats["probes"] += 1
            got = extract_ts(raw.decode("utf-8", "replace"))
            if got is not None:
                if got[0] >= target:
                    if before:
                        if prev is None:
                            return ("before_empty", 0, 0, b"")
                        return ("hit", prev[0], prev[1], prev[2])
                    return ("hit", offset, line_no, raw)
                prev = (offset, line_no, raw)
                last_seen = prev
            offset += len(raw)
    if before:
        if last_seen is None:
            return ("before_empty", 0, 0, b"")
        return ("hit", last_seen[0], last_seen[1], last_seen[2])
    return ("exhausted", 0, 0, b"")


def main(argv=None):
    _force_utf8()
    p = argparse.ArgumentParser(
        prog="log-time-locate.py",
        description="利用时间戳有序性二分定位某时刻在日志文件中的位置")
    p.add_argument("file", help="日志文件(二分模式要求时间戳非减)")
    p.add_argument("time", help='目标时刻, 如 "2024-06-01 12:00:00" 或 10 位 epoch 秒')
    p.add_argument("-A", "--after", type=int, default=0, metavar="N",
                   help="命中后额外打印后续 N 行")
    p.add_argument("--before", action="store_true",
                   help="改为定位目标时刻之前(严格早于)的最后一行")
    p.add_argument("--linear", action="store_true",
                   help="不用二分, 逐行线性扫描(日志乱序/时间戳缺失时用)")
    args = p.parse_args(argv)

    try:
        target = parse_target(args.time)
    except ValueError as e:
        print("[log-time-locate] %s" % e, file=sys.stderr)
        return 2
    if not os.path.isfile(args.file):
        print("[log-time-locate] 文件不存在: %s" % args.file, file=sys.stderr)
        return 2
    size = os.path.getsize(args.file)
    if size == 0:
        print("[log-time-locate] 文件为空, 无可定位内容")
        return 0

    stats = {"probes": 0, "blind": 0}
    try:
        if args.linear:
            status, start, line_no, raw = linear_locate(args.file, target, args.before, stats)
            how = "线性扫描 %d 行" % stats["probes"]
        else:
            offset = bisect_locate(args.file, target, stats)
            how = "二分 %d 次" % stats["probes"]
            if stats["blind"]:
                print("[log-time-locate] 警告: %d 次探测行未解析出时间戳, 结果可能偏移; "
                      "乱序日志请加 --linear" % stats["blind"], file=sys.stderr)
            status = "hit"
            start, line_no, raw = 0, 0, None
            if args.before:
                if offset <= 0:
                    status = "before_empty"
                else:
                    with open(args.file, "rb") as f:
                        start = line_start_prev(f, offset)
                    line_no = count_lines_before(args.file, start)
            else:
                if offset >= size:
                    status = "exhausted"
                else:
                    start = offset
                    line_no = count_lines_before(args.file, start)
    except OSError as e:
        print("[log-time-locate] 读取失败: %s" % e, file=sys.stderr)
        return 2

    if status == "before_empty":
        print("[log-time-locate] 未命中: 目标时刻不晚于首行时间, 没有更早的行")
        print("[log-time-locate] %s" % how)
        return 0
    if status == "exhausted":
        print("[log-time-locate] 未命中: 所有日志行都早于 %s" % args.time)
        print("[log-time-locate] %s" % how)
        return 0

    if raw is None:
        try:
            with open(args.file, "rb") as f:
                raw = read_line_at(f, start)
        except OSError as e:
            print("[log-time-locate] 读取失败: %s" % e, file=sys.stderr)
            return 2
    text = raw.decode("utf-8", "replace").rstrip("\r\n")
    got = extract_ts(text)
    print("命中: 第 %d 行, 字节偏移 %d" % (line_no, start))
    if got:
        print("行时间: %s (= %s)" % (got[1], fmt_ts(got[0])))
    print("内容: %s" % text)

    if args.after > 0:
        tail = []
        try:
            with open(args.file, "rb") as f:
                f.seek(start)
                f.readline()  # 跳过命中行本身
                for _ in range(args.after):
                    ln = f.readline()
                    if not ln:
                        break
                    tail.append(ln.decode("utf-8", "replace").rstrip("\r\n"))
        except OSError as e:
            print("[log-time-locate] 读取失败: %s" % e, file=sys.stderr)
            return 2
        if tail:
            print("后续 %d 行:" % len(tail))
            for ln in tail:
                print("  " + ln)
    print("[log-time-locate] %s" % how)
    return 0


if __name__ == "__main__":
    sys.exit(main())
