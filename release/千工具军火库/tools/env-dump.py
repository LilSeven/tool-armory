#!/usr/bin/env python3
"""环境变量导出器 (env-dump) —— 排序导出环境变量，标记超长或重复的路径类变量，支持 JSON 输出。

用途:
    按变量名排序导出环境变量并逐项体检:
      * LONG  值长度超过 --min-length（默认 1024 字符）；
      * DUP   路径类变量（值中含路径分隔符 os.pathsep）存在重复条目
              （Windows 下忽略大小写），并在 duplicates 字段列出重复的值。
    --set NAME=VALUE 可注入测试变量（只影响本进程副本，不改真实环境）；
    --only NAME[,NAME...] 只导出指定变量；--json 输出机器可读结果。

示例命令:
    python env-dump.py                    # 排序导出全部环境变量
    python env-dump.py --json             # JSON 输出
    python env-dump.py --set "MYPATH=a;b;a" --min-length 4 --only MYPATH

只依赖 Python 标准库；只读检查，不修改真实环境变量。
"""

import argparse
import json
import os
import sys


def _force_utf8_stdout():
    """管道/重定向场景下尽量以 UTF-8 输出，避免 Windows 默认码页导致乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (stream.encoding or "").lower().replace("-", "")
            if enc and enc != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def analyze(env, min_length):
    """对环境变量字典逐项体检，返回按变量名排序的记录列表。"""
    sep = os.pathsep
    fold = os.name == "nt"  # Windows 下路径大小写不敏感
    records = []
    for name in sorted(env, key=str.lower):
        value = env[name]
        flags = []
        dupes = []
        if sep in value:  # 含路径分隔符，视为路径类变量
            parts = [p.strip() for p in value.split(sep) if p.strip()]
            first_seen = {}
            for p in parts:
                key = p.lower() if fold else p
                if key in first_seen:
                    if first_seen[key] not in dupes:
                        dupes.append(first_seen[key])
                else:
                    first_seen[key] = p
            if dupes:
                flags.append("DUP")
        if len(value) > min_length:
            flags.append("LONG")
        records.append({"name": name, "length": len(value), "flags": flags,
                        "duplicates": dupes})
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="env-dump",
        description="环境变量导出器：排序导出并标记超长/路径重复的变量，支持 JSON 输出",
    )
    parser.add_argument("--min-length", type=int, default=1024,
                        help="超长变量的长度阈值（默认 1024 字符）")
    parser.add_argument("--set", dest="sets", action="append", default=[],
                        metavar="NAME=VALUE", help="注入测试变量 NAME=VALUE（可重复）")
    parser.add_argument("--only", default="", metavar="NAME[,NAME...]",
                        help="只导出指定变量，逗号分隔")
    parser.add_argument("--json", dest="as_json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args(argv)
    _force_utf8_stdout()

    env = dict(os.environ)
    for item in args.sets:
        if "=" not in item:
            parser.error("--set 需要 NAME=VALUE 格式，收到: %r" % item)
        name, _, value = item.partition("=")
        env[name.strip()] = value

    if args.only:
        wanted = [w.strip() for w in args.only.split(",") if w.strip()]
        if os.name == "nt":
            lower_map = {k.lower(): k for k in env}
            keys = [lower_map[w.lower()] for w in wanted if w.lower() in lower_map]
        else:
            keys = [w for w in wanted if w in env]
        env = {k: env[k] for k in keys}

    records = analyze(env, args.min_length)
    flagged = sum(1 for r in records if r["flags"])

    if args.as_json:
        print(json.dumps({"count": len(records), "flagged": flagged, "variables": records},
                         ensure_ascii=False, indent=2))
        return 0

    print("共 %d 个环境变量（按名称排序），其中 %d 个被标记: " % (len(records), flagged))
    for r in records:
        state = "/".join(r["flags"]) if r["flags"] else "-"
        extra = "  重复值: %s" % ", ".join(repr(d) for d in r["duplicates"]) if r["duplicates"] else ""
        print("  %-24s len=%-6d [%s]%s" % (r["name"], r["length"], state, extra))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
