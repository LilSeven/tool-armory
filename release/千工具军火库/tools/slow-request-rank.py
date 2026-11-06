#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""慢请求排行(slow-request-rank):解析访问日志耗时字段,列出最慢的 N 个请求。

自动识别(按行命中率选择, 达到 60%% 才采用):
  1. nginx/apache 组合格式末尾带耗时:
     1.2.3.4 - - [ts] "GET /a HTTP/1.1" 200 2326 "ref" "UA" 0.123 [upstream]
     (nginx $request_time / apache %T, 单位秒)
  2. JSON 日志: {"request_time":0.05} 或 {"duration_ms":123} 等键
  也可手动指定:
    --column N     按空白分列, 第 N 列(1 起始)为耗时
    --regex RE     自定义正则, 名为 time 的分组或第 1 个捕获组为耗时
    --unit s|ms|us 声明耗时单位(默认 auto: 跟随所识别模式的单位)

用法:
    python slow-request-rank.py [FILE ...] [-n N] [--asc]

示例:
    python -I slow-request-rank.py access.log -n 20
    python -I slow-request-rank.py api.jsonl -n 10
    cat access.log | python -I slow-request-rank.py -n 5

输出: 排行表(排名/耗时/状态码/请求/位置), 并注明所用模式、单位与识别率。
退出码: 0 成功; 1 无输入; 2 无法识别耗时字段(请用 --column/--regex)。
仅使用 Python 标准库。
"""

import argparse
import re
import sys

UNIT_FACTOR = {"s": 1.0, "ms": 1e-3, "us": 1e-6}

CANDIDATES = [
    ("combined/request_time", "full", "s",
     re.compile(r'^(?P<ip>\S+) \S+ \S+ \[[^\]]+\] "(?P<req>[^"]*)" '
                r'(?P<status>\d{3}) (?P<size>\S+)(?: "[^"]*" "[^"]*")? '
                r'(?P<time>\d+(?:\.\d+)?)(?:\s+\S+)*\s*$')),
    ("json-time(s)", "search", "s",
     re.compile(r'"(?:request_time|duration|elapsed|cost_time|cost|rt|took)"'
                r'\s*:\s*"?(?P<time>\d+(?:\.\d+)?)"?', re.IGNORECASE)),
    ("json-time(ms)", "search", "ms",
     re.compile(r'"(?:duration_ms|elapsed_ms|rt_ms|took_ms|cost_ms|time_ms)"'
                r'\s*:\s*"?(?P<time>\d+(?:\.\d+)?)"?', re.IGNORECASE)),
]

JSON_STATUS_RE = re.compile(r'"(?:status|code)"\s*:\s*"?(\d{3})"?', re.IGNORECASE)
JSON_PATH_RE = re.compile(r'"(?:path|url|uri)"\s*:\s*"([^"]*)"', re.IGNORECASE)


def _setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _fmt_num(v):
    s = ("%.6f" % v).rstrip("0").rstrip(".")
    return s if s else "0"


def _mk_row(value, unit, status, req, src, lineno):
    secs = value * UNIT_FACTOR[unit]
    return (secs, str(status), "%s:%d" % (src, lineno), req, _fmt_num(value) + unit)


def _read_records(paths):
    """读取全部行为 (line, 来源, 行号); 空行跳过。"""
    records = []
    for path in (paths or ["-"]):
        if path == "-":
            try:
                sys.stdin.reconfigure(errors="replace")
            except (AttributeError, ValueError):
                pass
            fh, name, do_close = sys.stdin, "<stdin>", False
        else:
            try:
                fh = open(path, "r", encoding="utf-8", errors="replace")
            except OSError as exc:
                print("错误: 无法打开 %s: %s" % (path, exc), file=sys.stderr)
                raise SystemExit(2)
            name, do_close = path, True
        try:
            for lineno, line in enumerate(fh, 1):
                line = line.rstrip("\r\n")
                if line.strip():
                    records.append((line, name, lineno))
        finally:
            if do_close:
                fh.close()
    return records


def pick_candidate(lines):
    """按命中率选择耗时模式; 返回 (命中数, 名称, 模式, 单位, 正则) 或 None。"""
    best = None
    for name, mode, unit, rex in CANDIDATES:
        hits = 0
        for line in lines:
            matched = rex.fullmatch(line) if mode == "full" else rex.search(line)
            if matched:
                hits += 1
        if hits >= 0.6 * len(lines) and (best is None or hits > best[0]):
            best = (hits, name, mode, unit, rex)
    return best


def parse_auto(mode, rex, line, src, lineno, unit):
    m = rex.fullmatch(line) if mode == "full" else rex.search(line)
    if not m:
        return None
    gd = m.groupdict()
    raw = gd.get("time")
    if raw is None:
        raw = m.group(1)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    req = gd.get("req")
    if not req:
        pm = JSON_PATH_RE.search(line)
        req = pm.group(1) if pm else line[:60]
    status = gd.get("status")
    if not status:
        sm = JSON_STATUS_RE.search(line)
        status = sm.group(1) if sm else "-"
    return _mk_row(value, unit, status, req, src, lineno)


def parse_custom(rex, line, src, lineno, unit):
    m = rex.search(line)
    if not m:
        return None
    gd = m.groupdict()
    raw = gd.get("time")
    if raw is None and m.groups():
        raw = m.group(1)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    req = gd.get("req") or gd.get("path") or line[:60]
    status = gd.get("status") or "-"
    return _mk_row(value, unit, status, req, src, lineno)


def parse_column(col, line, src, lineno, unit):
    parts = line.split()
    if col < 1 or col > len(parts):
        return None
    try:
        value = float(parts[col - 1])
    except ValueError:
        return None
    return _mk_row(value, unit, "-", line[:60], src, lineno)


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(
        prog="slow-request-rank",
        description="解析访问日志耗时字段, 列出最慢的 N 个请求")
    ap.add_argument("files", nargs="*",
                    help="日志文件(可多个); 缺省或 '-' 表示 stdin")
    ap.add_argument("-n", dest="top", type=int, default=10, metavar="N",
                    help="排行条数(默认 10)")
    ap.add_argument("--asc", action="store_true", help="升序输出(默认降序)")
    ap.add_argument("--column", type=int, default=None, metavar="N",
                    help="第 N 列(1 起始)为耗时")
    ap.add_argument("--regex", default=None, metavar="RE",
                    help="自定义耗时正则(time 分组或第 1 组)")
    ap.add_argument("--unit", choices=("auto", "s", "ms", "us"), default="auto",
                    help="耗时单位(默认 auto 跟随模式)")
    args = ap.parse_args(argv)

    records = _read_records(args.files)
    if not records:
        print("错误: 没有读到任何日志行", file=sys.stderr)
        return 1
    lines = [r[0] for r in records]

    auto_mode = auto_rex = None
    if args.regex:
        try:
            auto_rex = re.compile(args.regex)
        except re.error as exc:
            print("错误: 无效正则: %s" % exc, file=sys.stderr)
            return 2
        mode_desc, kind = "自定义正则", "regex"
        unit = "s" if args.unit == "auto" else args.unit
    elif args.column:
        mode_desc, kind = "第 %d 列" % args.column, "column"
        unit = "s" if args.unit == "auto" else args.unit
    else:
        picked = pick_candidate(lines)
        if picked is None:
            print("错误: 无法自动识别耗时字段(命中率不足 60%%), "
                  "请用 --column N 或 --regex 指定", file=sys.stderr)
            return 2
        _, mode_desc, auto_mode, cunit, auto_rex = picked
        kind = "auto"
        unit = cunit if args.unit == "auto" else args.unit

    rows = []
    for line, src, lineno in records:
        if kind == "regex":
            row = parse_custom(auto_rex, line, src, lineno, unit)
        elif kind == "column":
            row = parse_column(args.column, line, src, lineno, unit)
        else:
            row = parse_auto(auto_mode, auto_rex, line, src, lineno, unit)
        if row:
            rows.append(row)

    if not rows:
        print("错误: 没有解析到任何耗时数据", file=sys.stderr)
        return 2
    rows.sort(key=lambda r: r[0], reverse=not args.asc)

    if unit == "s":
        vals = [r[0] for r in rows]
        if all(abs(v - round(v)) < 1e-9 for v in vals) and max(vals) >= 1000:
            print("提示: 耗时全为整数且最大值较大(%s); 若该字段是微秒"
                  "(如 apache %%D), 请加 --unit us 重新运行" % _fmt_num(max(vals)),
                  file=sys.stderr)

    out = sys.stdout
    out.write("模式: %s  单位: %s  识别: %d/%d 行\n"
              % (mode_desc, unit, len(rows), len(records)))
    header = ("排名", "耗时", "状态", "请求", "位置")
    top = rows[: max(1, args.top)]
    w_time = max([len(r[4]) for r in top] + [len(header[1])])
    w_req = max([len(r[3]) for r in top] + [len(header[3])])
    w_src = max([len(r[2]) for r in top] + [len(header[4])])
    out.write("%-4s  %-*s  %-4s  %-*s  %s\n"
              % (header[0], w_time, header[1], header[2], w_req, header[3], header[4]))
    for i, row in enumerate(top, 1):
        out.write("%-4d  %-*s  %-4s  %-*s  %s\n"
                  % (i, w_time, row[4], row[1], w_req, row[3], row[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
