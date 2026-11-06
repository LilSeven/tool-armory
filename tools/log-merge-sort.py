#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多日志归并(log-merge-sort):把多个日志文件按时间戳归并成统一时间线。

对每个文件逐行识别行首时间戳, 统一按时间先后排序输出(稳定排序, 同一时刻的
行保持输入时的文件顺序+行号)。因不假定输入文件本身有序, 全部行会读入内存
(约 O(总行数); 超大日志请先切分或用外部排序)。无时间戳的行默认按原遇到
顺序附加到末尾(--unparsed drop 可丢弃)。

支持的行首时间戳(自动识别):
  2024-05-01T10:00:00 / 2024-05-01 10:00:00.123 / ...Z / ...+08:00 / ...+0800
  2024/05/01 10:00:00
  [01/May/2024:10:00:00 +0800]                 (Apache/CLF)
  1714538400 / 1714538400.5 / 1714538400123    (epoch 秒/毫秒)
  May  1 10:00:00                              (syslog, 年份取当前年)
带时区的时间统一换算成 UTC 再比较; 无时区按 UTC 处理。

用法:
    python log-merge-sort.py a.log b.log [-o out.log] [--show-source]
        [--unparsed {last,drop}]

示例:
    python -I log-merge-sort.py app.1.log app.2.log -o merged.log --show-source
    cat rotated*.log | python -I log-merge-sort.py -        # 单文件也可排序

仅使用 Python 标准库。
"""

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

ISO_RE = re.compile(
    r"^(\d{4})-(\d{1,2})-(\d{1,2})[T ](\d{1,2}):(\d{2}):(\d{2})"
    r"(?:[.,](\d{1,6}))?(?:\s*(Z|[+-]\d{2}:?\d{2}))?")
SLASH_RE = re.compile(
    r"^(\d{4})/(\d{1,2})/(\d{1,2})[T ](\d{1,2}):(\d{2}):(\d{2})(?:[.,](\d{1,6}))?")
CLF_RE = re.compile(
    r"^(\d{1,2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})"
    r"(?: ([+-])(\d{2})(\d{2}))?$")
SYSLOG_RE = re.compile(r"^([A-Za-z]{3}) +(\d{1,2}) (\d{1,2}):(\d{2}):(\d{2})\b")
EPOCH_MS_RE = re.compile(r"^(\d{13})(?:\.(\d+))?(?!\d)")
EPOCH_S_RE = re.compile(r"^(\d{10})(?:\.(\d+))?(?!\d)")


def _tz_from_str(tz_str):
    if tz_str == "Z":
        return timezone.utc
    sign = 1 if tz_str[0] == "+" else -1
    digits = tz_str[1:].replace(":", "")
    return timezone(sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:4])))


def _naive_utc(dt):
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _micro(frac):
    return int(frac.ljust(6, "0")) if frac else 0


def parse_line_ts(line):
    """识别行首时间戳, 返回 naive-UTC datetime; 识别失败返回 None。"""
    s = line.lstrip()
    if s.startswith("["):
        end = s.find("]")
        if end != -1:
            m = CLF_RE.match(s[1:end])
            if m:
                day, mon_s, year, hh, mi, ss, sign, oh, om = m.groups()
                mon = MONTHS.get(mon_s.lower())
                if mon:
                    dt = datetime(int(year), mon, int(day), int(hh), int(mi), int(ss))
                    if sign:
                        delta = timedelta(hours=int(oh), minutes=int(om))
                        dt = dt.replace(tzinfo=timezone(delta if sign == "+" else -delta))
                    return _naive_utc(dt)
    m = ISO_RE.match(s)
    if m:
        y, mo, d, hh, mi, ss, frac, tz = m.groups()
        dt = datetime(int(y), int(mo), int(d), int(hh), int(mi), int(ss), _micro(frac))
        if tz:
            dt = dt.replace(tzinfo=_tz_from_str(tz))
        return _naive_utc(dt)
    m = SLASH_RE.match(s)
    if m:
        y, mo, d, hh, mi, ss, frac = m.groups()
        dt = datetime(int(y), int(mo), int(d), int(hh), int(mi), int(ss), _micro(frac))
        return _naive_utc(dt)
    m = SYSLOG_RE.match(s)
    if m:
        mon_s, day, hh, mi, ss = m.groups()
        mon = MONTHS.get(mon_s.lower())
        if mon:
            try:
                return datetime(datetime.now().year, mon, int(day),
                                int(hh), int(mi), int(ss))
            except ValueError:
                return None
    m = EPOCH_MS_RE.match(s)
    if m:
        ts = int(m.group(1)) / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
    m = EPOCH_S_RE.match(s)
    if m:
        ts = float(m.group(1) + ("." + m.group(2) if m.group(2) else ""))
        return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
    return None


def _open_source(path):
    if path == "-":
        try:
            sys.stdin.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
        return sys.stdin, "<stdin>"
    try:
        return open(path, "r", encoding="utf-8", errors="replace"), path
    except OSError as exc:
        print("错误: 无法打开 %s: %s" % (path, exc), file=sys.stderr)
        raise SystemExit(2)


def _setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(
        prog="log-merge-sort",
        description="把多个日志文件按时间戳归并排序成统一时间线")
    ap.add_argument("files", nargs="*",
                    help="日志文件(可多个); 缺省或 '-' 表示 stdin")
    ap.add_argument("-o", "--output", metavar="FILE", help="输出文件(缺省 stdout)")
    ap.add_argument("--show-source", action="store_true",
                    help="每行前加 [文件:行号] 前缀")
    ap.add_argument("--unparsed", choices=("last", "drop"), default="last",
                    help="无时间戳行: 附加末尾(默认)或丢弃")
    args = ap.parse_args(argv)

    paths = args.files or ["-"]
    records = []  # (排序键, 行号, 来源名, 行)
    for idx, path in enumerate(paths):
        fh, name = _open_source(path)
        try:
            for lineno, line in enumerate(fh, 1):
                dt = parse_line_ts(line)
                key = (1, idx) if dt is None else (0, dt, idx)
                records.append((key, lineno, name, line))
        finally:
            if fh is not sys.stdin:
                fh.close()
    records.sort(key=lambda r: r[0])  # 稳定排序, 同键保持输入顺序

    out_fh = sys.stdout
    if args.output:
        try:
            out_fh = open(args.output, "w", encoding="utf-8",
                          errors="replace", newline="\n")
        except OSError as exc:
            print("错误: 无法写入 %s: %s" % (args.output, exc), file=sys.stderr)
            for fh in opened:
                fh.close()
            return 2

    total = kept = has_ts = 0
    try:
        for key, lineno, name, line in records:
            total += 1
            if key[0] == 1 and args.unparsed == "drop":
                continue
            kept += 1
            if key[0] == 0:
                has_ts += 1
            text = line if line.endswith("\n") else line + "\n"
            if args.show_source:
                text = "[%s:%d] %s" % (name, lineno, text)
            out_fh.write(text)
    finally:
        if out_fh is not sys.stdout:
            out_fh.close()

    dropped = total - kept
    print("归并完成: 读入 %d 行, 输出 %d 行 (有时间戳 %d 行, 无时间戳 %d 行%s)"
          % (total, kept, has_ts, kept - has_ts,
             (", 丢弃 %d 行" % dropped) if dropped else ""),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
