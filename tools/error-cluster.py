#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""error-cluster — 错误聚类去重。

把日志消息中的数字、IP、UUID、十六进制 ID 等易变部分归一化为占位符
(<N>/<IP>/<UUID>/<HEX>) 得到"消息模板"，再按模板聚类并按出现次数排序。
同一种错误刷 1000 遍也只占一行，一眼看清"到底有几种错、哪种最多"。

默认只聚类 ERROR/FATAL 行；加 --all 聚类全部日志行。

用法:
  python error-cluster.py <日志文件|-> [--all] [--top 20] [--min-count 1]

示例:
  python error-cluster.py app.log
  python error-cluster.py app.log --top 10 --min-count 2
  tail -n 2000 app.log | python error-cluster.py - --all
"""

import argparse
import re
import sys

LEVEL_RE = re.compile(
    r"\b(TRACE|DEBUG|INFO|NOTICE|WARNING|WARN|ERROR|ERR|FATAL|CRITICAL)\b")
LEVEL_RE_LOOSE = re.compile(LEVEL_RE.pattern, re.IGNORECASE)
LEVEL_SYNONYM = {"WARNING": "WARN", "ERR": "ERROR", "CRITICAL": "FATAL"}
ERROR_LEVELS = ("ERROR", "FATAL")

_RE_ISO = re.compile(
    r"\b(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:[.,](\d{1,6}))?")
_RE_SLASH = re.compile(
    r"\b(\d{4})/(\d{2})/(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:[.,](\d{1,6}))?")
_RE_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_RE_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_RE_HEX = re.compile(r"\b[0-9a-fA-F]{8,}\b")
_RE_NUM = re.compile(r"\d+")
_RE_WS = re.compile(r"\s+")


def detect_level(line):
    m = LEVEL_RE.search(line)
    if m:
        return LEVEL_SYNONYM.get(m.group(1), m.group(1))
    m = LEVEL_RE_LOOSE.search(line)
    if m:
        return LEVEL_SYNONYM.get(m.group(1).upper(), m.group(1).upper())
    return None


def make_template(line):
    """去掉时间戳与级别词，再把易变片段归一为占位符，得到消息模板。"""
    s = line
    m = _RE_ISO.search(s)
    if m is None:
        m = _RE_SLASH.search(s)
    if m is not None:
        s = s[:m.start()] + " " + s[m.end():]
    m = LEVEL_RE.search(s)
    if m is not None:
        s = s[:m.start()] + " " + s[m.end():]
    s = _RE_UUID.sub("<UUID>", s)
    s = _RE_IP.sub("<IP>", s)
    s = _RE_HEX.sub("<HEX>", s)
    s = _RE_NUM.sub("<N>", s)
    return _RE_WS.sub(" ", s).strip()


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        description="错误日志按消息模板聚类去重并按出现次数排序")
    ap.add_argument("file", help="日志文件路径, 传 - 读标准输入")
    ap.add_argument("--all", action="store_true",
                    help="聚类全部日志行 (默认只聚类 ERROR/FATAL 行)")
    ap.add_argument("--top", type=int, default=20,
                    help="最多显示前 N 类 (默认 20, 0=不限制)")
    ap.add_argument("--min-count", type=int, default=1,
                    help="只显示出现次数 >= 该值的类 (默认 1)")
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
    err_lines = 0
    clusters = {}  # 模板 -> [出现次数, 首条原始行]
    try:
        for line in fh:
            total += 1
            if not args.all:
                lv = detect_level(line)
                if lv is None or lv not in ERROR_LEVELS:
                    continue
            err_lines += 1
            tpl = make_template(line)
            ent = clusters.get(tpl)
            if ent is None:
                clusters[tpl] = [1, line.strip()]
            else:
                ent[0] += 1
    finally:
        if need_close:
            fh.close()

    items = [(t, c, ex) for t, (c, ex) in clusters.items()
             if c >= args.min_count]
    items.sort(key=lambda x: -x[1])  # sorted 稳定: 同次数保持首现顺序
    shown = items[:args.top] if args.top > 0 else items

    scope = "全部日志" if args.all else "ERROR/FATAL"
    print("错误聚类: 共扫描 {} 行, 其中 {} 行 {} 行, 归并为 {} 类".format(
        total, err_lines, scope, len(items)))
    if err_lines == 0 and not args.all:
        print("提示: 未发现 ERROR/FATAL 行; 若想聚类全部日志请加 --all",
              file=sys.stderr)
    for i, (tpl, c, ex) in enumerate(shown, 1):
        pct = c * 100.0 / err_lines if err_lines else 0.0
        print("{:>3}  {:>6}  {:>5.1f}%  {}".format(i, c, pct, tpl[:120]))
        print("           例: {}".format(ex[:120]))
    if len(items) > len(shown):
        hidden_lines = sum(c for _, c, _ in items[len(shown):])
        print("... 其余 {} 类共 {} 行未显示 (可用 --top 调整)".format(
            len(items) - len(shown), hidden_lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
