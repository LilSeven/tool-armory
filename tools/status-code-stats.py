#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""状态码分布(status-code-stats):解析 HTTP 访问日志,统计状态码次数与占比。

自动识别状态码字段:
  1. CLF/组合日志: 引号包裹的请求行之后紧跟三位状态码;
  2. JSON 日志: "status"/"status_code"/"code" 键;
  3. 兜底: 多数行中处于同一空白分列、形如 1xx~5xx 的数字列。
也可用 --column N / --regex RE 手动指定(status 分组或第 1 个捕获组)。

用法:
    python status-code-stats.py [FILE ...] [--json] [--column N] [--regex RE]

示例:
    python -I status-code-stats.py access.log
    cat access.log | python -I status-code-stats.py --json

输出: 各状态码的次数/占比/条形图, 以及 2xx/3xx/4xx/5xx 分类汇总。
退出码: 0 成功(即使有未识别行); 1 无输入; 2 无法识别状态码字段。
仅使用 Python 标准库。
"""

import argparse
import json
import re
import sys
from collections import Counter

CLF_RE = re.compile(r'"[^"]*" (?P<status>\d{3}) (?P<size>\S+)')
JSON_RE = re.compile(r'"(?:status|status_code|code)"\s*:\s*"?(?P<status>\d{3})"?',
                     re.IGNORECASE)
TOKEN_RE = re.compile(r'"[^"]*"|\[[^\]]*\]|\S+')
STATUS_TOKEN_RE = re.compile(r"[1-5]\d{2}")


def _setup_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


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


def make_extract_regex(rex):
    def extract(line):
        m = rex.search(line)
        if not m:
            return None
        gd = m.groupdict()
        raw = gd.get("status") if "status" in gd else (m.group(1) if m.groups() else None)
        if raw and re.fullmatch(r"\d{3}", raw):
            return raw
        return None
    return extract


def make_extract_column(col):
    def extract(line):
        toks = TOKEN_RE.findall(line)
        if 1 <= col <= len(toks) and re.fullmatch(r"[1-5]\d{2}", toks[col - 1]):
            return toks[col - 1]
        return None
    return extract


def auto_pick(lines):
    """返回 (模式描述, extract 函数); 全部失败返回 (None, None)。"""
    def builtin_extract(rex):
        def extract(line):
            m = rex.search(line)
            return m.group("status") if m else None
        return extract

    best = None
    for name, rex in (("combined/clf", CLF_RE), ("json-status", JSON_RE)):
        hits = sum(1 for line in lines if rex.search(line))
        if hits >= 0.6 * len(lines) and (best is None or hits > best[0]):
            best = (hits, name, rex)
    if best:
        return best[1], builtin_extract(best[2])
    # 兜底: 找"多数行中同一列均为 1xx-5xx 数字"的列
    token_lines = [TOKEN_RE.findall(line) for line in lines]
    ncols = max((len(t) for t in token_lines), default=0)
    best_col, best_hits = None, 0
    for i in range(min(ncols, 64)):
        hits = sum(1 for t in token_lines
                   if i < len(t) and STATUS_TOKEN_RE.fullmatch(t[i]))
        if hits > best_hits:
            best_col, best_hits = i, hits
    if best_col is not None and best_hits >= 0.6 * len(lines):
        return "第 %d 列(自动)" % (best_col + 1), make_extract_column(best_col + 1)
    return None, None


def main(argv=None):
    _setup_stdio()
    ap = argparse.ArgumentParser(
        prog="status-code-stats",
        description="解析 HTTP 访问日志, 统计状态码分布")
    ap.add_argument("files", nargs="*",
                    help="日志文件(可多个); 缺省或 '-' 表示 stdin")
    ap.add_argument("--column", type=int, default=None, metavar="N",
                    help="第 N 列(1 起始)为状态码")
    ap.add_argument("--regex", default=None, metavar="RE",
                    help="自定义正则(status 分组或第 1 组)")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出统计结果")
    args = ap.parse_args(argv)

    records = _read_records(args.files)
    if not records:
        print("错误: 没有读到任何日志行", file=sys.stderr)
        return 1
    lines = [r[0] for r in records]
    total = len(lines)

    if args.regex:
        try:
            rex = re.compile(args.regex)
        except re.error as exc:
            print("错误: 无效正则: %s" % exc, file=sys.stderr)
            return 2
        mode_desc, extract = "自定义正则", make_extract_regex(rex)
    elif args.column:
        mode_desc, extract = "第 %d 列" % args.column, make_extract_column(args.column)
    else:
        mode_desc, extract = auto_pick(lines)
        if extract is None:
            print("错误: 无法自动识别状态码字段, 请用 --column N 或 --regex 指定",
                  file=sys.stderr)
            return 2

    counter = Counter()
    parsed = 0
    for line, _src, _lineno in records:
        code = extract(line)
        if code:
            counter[code] += 1
            parsed += 1

    if not parsed:
        print("错误: 未识别出任何状态码; 可用 --column N 或 --regex 指定字段",
              file=sys.stderr)
        return 2

    classes = Counter()
    for code, cnt in counter.items():
        classes[code[0] + "xx"] += cnt

    if args.json:
        payload = {
            "mode": mode_desc,
            "total_lines": total,
            "parsed": parsed,
            "unparsed": total - parsed,
            "codes": {c: n for c, n in counter.most_common()},
            "classes": {k: classes[k] for k in sorted(classes)},
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    out = sys.stdout
    out.write("模式: %s  共 %d 行, 识别 %d 行, 未识别 %d 行\n\n"
              % (mode_desc, total, parsed, total - parsed))
    max_cnt = max(counter.values())
    out.write("%-8s  %6s  %8s  %s\n" % ("状态码", "次数", "占比", "分布"))
    for code, cnt in counter.most_common():
        bar = "█" * max(1, round(30 * cnt / max_cnt))
        out.write("%-8s  %6d  %7.1f%%  %s\n"
                  % (code, cnt, 100.0 * cnt / parsed, bar))
    out.write("\n分类汇总: ")
    out.write("  ".join("%s=%d(%.1f%%)" % (k, classes[k], 100.0 * classes[k] / parsed)
                        for k in sorted(classes)))
    out.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
