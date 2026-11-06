#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""JSON日志美化 — 逐行解析 JSON 日志(JSONL), 格式化输出, 支持字段筛选与排序。

用法:
  python json-log-pretty.py app.jsonl                          # 每条按缩进美化输出
  python json-log-pretty.py app.jsonl --compact                # 压成单行
  python json-log-pretty.py app.jsonl --filter level=ERROR     # 筛选, 可重复(AND)
  python json-log-pretty.py app.jsonl --filter user.name=bo
  python json-log-pretty.py app.jsonl --sort-by ts --desc      # 按字段倒序
  python json-log-pretty.py app.jsonl --fields ts,level,msg    # 只保留/重排字段
  python json-log-pretty.py app.jsonl --sort-keys --limit 10
  tail -f app.jsonl | python json-log-pretty.py --compact      # 支持 stdin 流式

说明:
  * --filter KEY=VALUE 可重复(AND 关系); KEY 支持点路径(如 user.name);
    两侧都能转数字时按数值比较, 否则按字符串/JSON 字面比较。
  * --sort-by FIELD 需整份读入内存, 大文件慎用; 缺失该字段的记录排在最后。
    不加 --sort-by 时流式输出, 可配合 tail -f。
  * 解析失败的行默认跳过并在 stderr 提示行号; --raw 原样透传, --strict 遇坏行退出码 1。
  * 输出 UTF-8。退出码: 0 成功; 1 strict 模式遇到坏行; 2 参数或文件错误。
"""

import argparse
import json
import sys


def _force_utf8():
    """Windows 控制台/管道下强制 UTF-8。"""
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def get_field(obj, dotted):
    """按点路径取值, 返回 (值, 是否存在)。"""
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None, False
    return cur, True


def to_float(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    return None


def matches(rec, key, want):
    v, ok = get_field(rec, key)
    if not ok:
        return False
    fv, fw = to_float(v), to_float(want)
    if fv is not None and fw is not None:
        return fv == fw
    if isinstance(v, str):
        return v == want
    return json.dumps(v, ensure_ascii=False, sort_keys=True) == want


def sort_key(v):
    """可比较的排序键: 数字 < 字符串; 缺失字段单独排最后。"""
    f = to_float(v)
    if f is not None:
        return (0, f, "")
    if isinstance(v, str):
        return (1, 0.0, v)
    return (1, 0.0, json.dumps(v, ensure_ascii=False, sort_keys=True))


def main(argv=None):
    _force_utf8()
    p = argparse.ArgumentParser(
        prog="json-log-pretty.py",
        description="逐行解析 JSON 日志, 格式化输出并支持字段筛选与排序")
    p.add_argument("input", nargs="?", default="-",
                   help="输入 JSONL 文件, 缺省或 '-' 表示 stdin")
    p.add_argument("-o", "--output", help="输出文件, 缺省为 stdout")
    p.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE",
                   help="筛选条件, 可重复(AND)")
    p.add_argument("--fields", metavar="F1,F2", help="只保留这些字段(可调顺序, 支持点路径)")
    p.add_argument("--sort-by", dest="sort_by", metavar="FIELD", help="按字段排序(需整读内存)")
    p.add_argument("--desc", action="store_true", help="倒序(配合 --sort-by)")
    p.add_argument("--sort-keys", action="store_true", help="输出时按 key 排序")
    p.add_argument("--compact", action="store_true", help="每条压成单行")
    p.add_argument("--indent", type=int, default=2, metavar="N", help="缩进空格数, 默认 2")
    p.add_argument("--limit", type=int, metavar="N", help="只输出前 N 条")
    p.add_argument("--raw", action="store_true", help="解析失败的行原样透传")
    p.add_argument("--strict", action="store_true", help="遇到解析失败的行立即退出码 1")
    args = p.parse_args(argv)

    filters = []
    for spec in args.filter:
        key, sep, val = spec.partition("=")
        if not sep or not key:
            print("[json-log-pretty] --filter 需形如 KEY=VALUE: %r" % spec, file=sys.stderr)
            return 2
        filters.append((key, val))
    if args.fields is not None:
        field_names = [f.strip() for f in args.fields.split(",") if f.strip()]
        if not field_names:
            print("[json-log-pretty] --fields 为空", file=sys.stderr)
            return 2
    else:
        field_names = None
    if args.limit is not None and args.limit < 0:
        print("[json-log-pretty] --limit 不能为负", file=sys.stderr)
        return 2

    try:
        if args.input == "-":
            fin = sys.stdin
        else:
            fin = open(args.input, "r", encoding="utf-8", errors="replace")
    except OSError as e:
        print("[json-log-pretty] 无法打开输入: %s" % e, file=sys.stderr)
        return 2

    bad = []
    n_out = 0

    def emit(obj):
        data = obj
        if field_names is not None:
            data = {}
            for name in field_names:
                v, ok = get_field(obj, name)
                if ok:
                    data[name] = v
        fout.write(json.dumps(data, ensure_ascii=False, sort_keys=args.sort_keys,
                              indent=None if args.compact else max(0, args.indent)) + "\n")

    def keep(obj):
        return all(matches(obj, k, v) for k, v in filters)

    def bad_line(line_no, s):
        """记录坏行; strict 模式返回 True 表示应终止。"""
        bad.append(line_no)
        if args.strict:
            print("[json-log-pretty] 第 %d 行不是合法 JSON: %s" % (line_no, s[:80]),
                  file=sys.stderr)
            return True
        if args.raw:
            fout.write(s + "\n")
        return False

    fout = None
    try:
        if args.output is None:
            fout = sys.stdout
        else:
            fout = open(args.output, "w", encoding="utf-8", newline="")
        with fin:
            if args.sort_by:
                buf = []
                for line_no, raw in enumerate(fin, 1):
                    s = raw.strip()
                    if not s:
                        continue
                    try:
                        obj = json.loads(s)
                    except ValueError:
                        if bad_line(line_no, s):
                            return 1
                        continue
                    if keep(obj):
                        buf.append(obj)
                present = [o for o in buf if get_field(o, args.sort_by)[1]]
                missing = [o for o in buf if not get_field(o, args.sort_by)[1]]
                present.sort(key=lambda o: sort_key(get_field(o, args.sort_by)[0]),
                             reverse=args.desc)
                out_list = present + missing
                if args.limit is not None:
                    out_list = out_list[:args.limit]
                for obj in out_list:
                    emit(obj)
                    n_out += 1
            else:
                for line_no, raw in enumerate(fin, 1):
                    s = raw.strip()
                    if not s:
                        continue
                    try:
                        obj = json.loads(s)
                    except ValueError:
                        if bad_line(line_no, s):
                            return 1
                        continue
                    if keep(obj):
                        emit(obj)
                        n_out += 1
                        if args.limit is not None and n_out >= args.limit:
                            break
    except BrokenPipeError:
        try:
            import os
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        except OSError:
            pass
        return 0
    except OSError as e:
        print("[json-log-pretty] 读写失败: %s" % e, file=sys.stderr)
        return 2
    finally:
        if fout is not None and fout is not sys.stdout:
            fout.close()

    msg = "[json-log-pretty] 输出 %d 条" % n_out
    if bad:
        shown = ", ".join(map(str, bad[:5])) + ("..." if len(bad) > 5 else "")
        msg += "; 跳过 %d 个无法解析的行(行 %s)" % (len(bad), shown)
    print(msg, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
