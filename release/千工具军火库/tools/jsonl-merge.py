#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jsonl-merge —— 合并多个 JSONL 文件,可按字段排序、可选去重。

用途:
    读取多个 JSONL(每行一个 JSON 值)文件,解析后按指定字段排序(或保持
    输入行序),可选整行去重/按字段去重,统一输出为一个 JSONL 文件。
    仅用 Python 标准库,适用于 JSON Lines(.jsonl/.ndjson)日志与数据集合并。

用法:
    python jsonl-merge.py [-o OUT] [-k FIELD] [-d] [--dedup-key FIELD]
                          [--reverse] FILE [FILE ...]

示例:
    python jsonl-merge.py -o merged.jsonl a.jsonl b.jsonl       # 行序合并
    python jsonl-merge.py -k score -d -o top.jsonl part*.jsonl  # 按分数升序+去重
    python jsonl-merge.py -k user.name --reverse -o r.jsonl logs/*.jsonl
    cat a.jsonl | python jsonl-merge.py -k id -o out.jsonl -    # '-' 为标准输入

选项:
    FILE                输入文件,至少一个;支持通配符;"-" 表示标准输入
    -o, --output PATH   输出文件(缺省写到标准输出)
    -k, --key FIELD     按字段排序,支持点号路径(如 user.name);
                        缺省保持输入行序(稳定排序,同键保持原有相对顺序)
    -d, --dedup         去重:缺省按整行规范化 JSON 比较
    --dedup-key FIELD   改按该字段值去重(使用它即自动启用去重)
    --reverse           逆序输出

行为与退出码:
    0 成功;2 用法错误/文件不存在/存在非法 JSON 行(错误指明文件与行号)。
    排序键规则:数字与数字比、字符串与字符串比、其余按规范化 JSON 比;
    缺失排序字段的行排在最后(--reverse 时自然排最前)。
    输出为紧凑 JSON、非 ASCII 不转义;统计信息写标准错误,不污染输出流。
"""

import argparse
import glob
import json
import sys

MISSING = object()


def setup_stdio():
    """Windows 管道/重定向下强制 UTF-8 输出,避免 GBK 编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def lookup(obj, dotted):
    """按点号路径取字段,取不到返回 MISSING。"""
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return MISSING
    return cur


def sort_key(value):
    """混合类型安全排序键:(类别, 数值, 字符串)。数字<字符串<其他<缺失。"""
    if value is MISSING:
        return (3, 0.0, "")
    if isinstance(value, (int, float)):  # bool 是 int 子类,按数字参与排序
        return (0, float(value), "")
    if isinstance(value, str):
        return (1, 0.0, value)
    return (2, 0.0, json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def read_jsonl(path, records, stats):
    if path == "-":
        text, origin = sys.stdin.read(), "<stdin>"
    else:
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                text = fh.read()
        except OSError as exc:
            print("读取失败: %s (%s)" % (path, exc.strerror or exc),
                  file=sys.stderr)
            raise SystemExit(2)
        origin = path
    for lineno, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s:
            continue  # 跳过空行
        try:
            obj = json.loads(s)
        except json.JSONDecodeError as exc:
            print("%s:%d: 非法 JSON 行(%s)" % (origin, lineno, exc.msg),
                  file=sys.stderr)
            raise SystemExit(2)
        records.append(obj)
        stats["lines"] += 1


def expand_inputs(raw):
    paths = []
    for arg in raw:
        if "*" in arg or "?" in arg:
            hits = sorted(glob.glob(arg))
            if not hits:
                print("没有匹配到文件: %s" % arg, file=sys.stderr)
                raise SystemExit(2)
            paths.extend(hits)
        else:
            paths.append(arg)
    return paths


def main(argv=None):
    setup_stdio()
    ap = argparse.ArgumentParser(
        prog="jsonl-merge.py",
        description="合并多个 JSONL 文件,可按字段排序、可选去重(详见文件顶部 docstring)。",
    )
    ap.add_argument("inputs", nargs="*", metavar="FILE",
                    help="输入文件,支持通配符,'-' 为标准输入")
    ap.add_argument("-o", "--output", metavar="PATH", help="输出文件,缺省标准输出")
    ap.add_argument("-k", "--key", metavar="FIELD", help="排序字段,支持点号路径")
    ap.add_argument("-d", "--dedup", action="store_true", help="整行规范化 JSON 去重")
    ap.add_argument("--dedup-key", metavar="FIELD", help="按字段值去重(自动启用去重)")
    ap.add_argument("--reverse", action="store_true", help="逆序输出")
    args = ap.parse_args(argv)

    if not args.inputs:
        ap.error("至少需要一个输入 FILE(可用 '-' 读标准输入)")

    records, stats = [], {"lines": 0, "dup": 0}
    paths = expand_inputs(args.inputs)
    for path in paths:
        read_jsonl(path, records, stats)

    if args.key:
        records.sort(key=lambda o: sort_key(lookup(o, args.key)),
                     reverse=args.reverse)
    elif args.reverse:
        records.reverse()

    if args.dedup or args.dedup_key:
        seen, uniq = set(), []
        for obj in records:
            if args.dedup_key:
                v = lookup(obj, args.dedup_key)
                key = ("<missing>" if v is MISSING
                       else json.dumps(v, ensure_ascii=False, sort_keys=True, default=str))
            else:
                key = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
            if key in seen:
                stats["dup"] += 1
                continue
            seen.add(key)
            uniq.append(obj)
        records = uniq

    payload = "".join(
        json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
        for obj in records
    )
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
    else:
        sys.stdout.write(payload)

    print("已读取 %d 行(来自 %d 个文件), 输出 %d 行, 去重删除 %d 行"
          % (stats["lines"], len(paths), len(records), stats["dup"]),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
