#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""日志转CSV — 按可配置的行格式把日志解析成字段, 导出 CSV 或 JSON Lines(NDJSON)。

两种指定行格式的方式:
  1) --format 模板: {字段名} 占位, 默认惰性匹配(位于模板末尾的字段贪婪收尾);
     可用 {字段:正则} 显式指定该字段的匹配模式, 如 {ts:\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}}。
  2) --regex 完整正则: 使用命名分组 (?P<name>...)。

用法:
  python log-to-csv.py app.log -o out.csv
  python log-to-csv.py app.log --format "{ts} [{level}] {msg}" -o out.csv
  python log-to-csv.py app.log --format "{ts:\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}} {level} {msg}" --json -o out.jsonl
  python log-to-csv.py app.log --regex '^(?P<ts>\S+ \S+) (?P<level>\w+) (?P<msg>.*)$'
  python log-to-csv.py app.log --fields level,ts,msg --delimiter ';'
  cat app.log | python log-to-csv.py --json

默认格式: {ts:\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[.,]\d+)?} {level} {msg}
未匹配的行默认跳过并在 stderr 汇总; --keep-unmatched 时整行放进 raw 列保留。
字段值均为字符串; 输出 UTF-8, CSV 使用 \n 行尾。
退出码: 0 成功(含部分行未匹配); 2 参数或文件错误。
"""

import argparse
import csv
import json
import re
import sys

DEFAULT_FORMAT = r"{ts:\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[.,]\d+)?} {level} {msg}"
# {name} 或 {name:pattern}, pattern 内允许再嵌一层 {n}(如 \d{4})
PLACEHOLDER = re.compile(r"\{([A-Za-z_]\w*)(?::((?:[^{}]|\{[^{}]*\})*))?\}")


def _force_utf8():
    """Windows 控制台/管道下强制 UTF-8。"""
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def template_to_regex(tmpl):
    """把 '{a} {b:\d+} {c}' 转成带命名分组的正则。返回 (compiled, [字段名])。"""
    matches = list(PLACEHOLDER.finditer(tmpl))
    if not matches:
        raise ValueError("模板中没有 {字段} 占位符: %r" % tmpl)
    parts = []
    fields = []
    pos = 0
    for m in matches:
        parts.append(re.escape(tmpl[pos:m.start()]))
        name, pat = m.group(1), m.group(2)
        if name in fields:
            raise ValueError("字段名重复: %r" % name)
        fields.append(name)
        if pat is not None:
            body = pat
        elif m is matches[-1] and m.end() == len(tmpl):
            body = ".*"     # 末尾字段贪婪收尾
        else:
            body = ".*?"    # 其余惰性匹配
        parts.append("(?P<%s>%s)" % (name, body))
        pos = m.end()
    parts.append(re.escape(tmpl[pos:]))
    return re.compile("".join(parts)), fields


def main(argv=None):
    _force_utf8()
    p = argparse.ArgumentParser(
        prog="log-to-csv.py",
        description="按可配置的行格式把日志解析成字段, 导出 CSV 或 JSON Lines")
    p.add_argument("input", nargs="?", default="-",
                   help="输入日志文件, 缺省或 '-' 表示 stdin")
    p.add_argument("-o", "--output", help="输出文件, 缺省为 stdout")
    fmt = p.add_mutually_exclusive_group()
    fmt.add_argument("--format", metavar="TPL",
                     help="行格式模板, 如 '{ts} {level} {msg}'")
    fmt.add_argument("--regex", metavar="PATTERN",
                     help="完整正则, 使用命名分组 (?P<name>...)")
    p.add_argument("--fields", metavar="F1,F2",
                   help="只输出这些字段(可调顺序), 逗号分隔")
    p.add_argument("--json", action="store_true",
                   help="输出 JSON Lines 而非 CSV")
    p.add_argument("--delimiter", default=",",
                   help="CSV 分隔符, 默认 ','(传 \\\\t 表示制表符)")
    p.add_argument("--keep-unmatched", action="store_true",
                   help="未匹配的行不跳过, 整行放进 raw 字段保留")
    p.add_argument("--no-header", action="store_true", help="CSV 不写表头")
    args = p.parse_args(argv)

    try:
        if args.regex:
            rx = re.compile(args.regex)
            fields = list(rx.groupindex.keys())
            if not fields:
                raise ValueError("--regex 需要至少一个命名分组 (?P<name>...)")
        else:
            rx, fields = template_to_regex(args.format if args.format is not None
                                           else DEFAULT_FORMAT)
        if args.fields is not None:
            sel = [f.strip() for f in args.fields.split(",") if f.strip()]
        else:
            sel = list(fields)
        unknown = [f for f in sel if f not in fields]
        if unknown:
            raise ValueError("--fields 含未定义字段: %s (可用: %s)"
                             % (",".join(unknown), ",".join(fields)))
        if not sel:
            raise ValueError("--fields 为空")
        out_fields = sel + (["raw"] if args.keep_unmatched and "raw" not in sel else [])
    except (ValueError, re.error) as e:
        print("[log-to-csv] 参数错误: %s" % e, file=sys.stderr)
        return 2

    delim = args.delimiter
    if delim == "\\t":
        delim = "\t"
    delim = delim[:1] or ","

    try:
        if args.input == "-":
            fin = sys.stdin
        else:
            fin = open(args.input, "r", encoding="utf-8", errors="replace")
    except OSError as e:
        print("[log-to-csv] 无法打开输入: %s" % e, file=sys.stderr)
        return 2

    n_ok = n_skip = n_raw = 0
    fout = None
    try:
        if args.output is None:
            fout = sys.stdout
        else:
            fout = open(args.output, "w", encoding="utf-8", newline="")
        w = None
        if not args.json:
            w = csv.writer(fout, delimiter=delim, lineterminator="\n")
            if not args.no_header:
                w.writerow(out_fields)
        with fin:
            for line in fin:
                line = line.rstrip("\r\n")
                m = rx.fullmatch(line)
                if m:
                    n_ok += 1
                    rec = {k: (m.group(k) or "") for k in sel}
                    if args.keep_unmatched and "raw" in out_fields and "raw" not in rec:
                        rec["raw"] = ""
                else:
                    n_skip += 1
                    if not args.keep_unmatched:
                        continue
                    n_raw += 1
                    rec = {k: "" for k in sel}
                    rec["raw"] = line
                if args.json:
                    fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                else:
                    w.writerow([rec.get(k, "") for k in out_fields])
    except BrokenPipeError:
        try:
            import os
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        except OSError:
            pass
        return 0
    except (OSError, re.error) as e:
        print("[log-to-csv] 读写失败: %s" % e, file=sys.stderr)
        return 2
    finally:
        if fout is not None and fout is not sys.stdout:
            fout.close()

    msg = "[log-to-csv] 解析 %d 行, 跳过 %d 行" % (n_ok, n_skip)
    if n_raw:
        msg += " (其中 %d 行以 raw 保留)" % n_raw
    print(msg, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
