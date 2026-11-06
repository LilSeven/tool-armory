#!/usr/bin/env python3
r"""会话日志归组 (session-log-split): 按请求 ID/会话 ID 把交错的日志行归组。

用途:
    读入交错的日志(文件或标准输入), 逐行提取请求/会话标识, 按标识归组,
    以会话为单位重组输出该请求的完整日志(保持原顺序), 未归组行单独列出。
    默认依次尝试以下模式, 命中即止:
      1. request_id/req_id/session_id/trace_id/correlation_id 的 k=v 或 k: v 形式
      2. [req-xxx] / [session xxx] / [trace-xxx] 方括号形式
      3. UUID
    可用 --id-regex 指定自定义正则: 含捕获组时取第一个非空组, 否则取整个匹配。

示例命令:
    python -I session-log-split.py server.log
    python -I session-log-split.py --only A100 server.log      # 只看指定会话
    python -I session-log-split.py --summary server.log        # 只看每个会话概要
    python -I session-log-split.py --id-regex "trace=([a-f0-9]+)" server.log
    cat server.log | python -I session-log-split.py

退出码: 0 成功; 1 --only 指定的会话不存在; 2 参数错误或文件读取失败。
"""

import argparse
import re
import sys

DEFAULT_PATTERNS = [
    re.compile(
        r"(?:request[_-]?id|req[_-]?id|session[_-]?id|trace[_-]?id|correlation[_-]?id)"
        r"[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9][A-Za-z0-9_.\-]*)",
        re.I),
    re.compile(r"\[(?:req|request|session|trace)[-_ ]([A-Za-z0-9][A-Za-z0-9_.\-]*)\]", re.I),
    re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
]


def extract_id(line, patterns):
    """按顺序尝试各模式提取会话 ID; 提取不到返回 None。"""
    for rx in patterns:
        mobj = rx.search(line)
        if not mobj:
            continue
        if mobj.re.groups:
            for grp in mobj.groups():
                if grp:
                    return grp
            return None
        return mobj.group(0)
    return None


def stream_setup():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def iter_lines(paths):
    if not paths:
        for line in sys.stdin:
            yield line
        return
    for path in paths:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                yield line


def main(argv=None):
    stream_setup()
    parser = argparse.ArgumentParser(
        prog="session-log-split",
        description="按请求 ID/会话 ID 把交错的日志行归组, 重组单个请求的完整日志。")
    parser.add_argument("files", nargs="*", help="日志文件; 缺省读标准输入")
    parser.add_argument("--id-regex", default=None, metavar="REGEX",
                        help="自定义 ID 提取正则; 含捕获组取第一个非空组, 否则取整个匹配")
    parser.add_argument("--only", default=None, metavar="ID", help="只输出指定会话")
    parser.add_argument("--summary", action="store_true", help="只输出每个会话的行数与首行预览")
    parser.add_argument("--drop-ungrouped", action="store_true", help="不输出未归组行")
    args = parser.parse_args(argv)

    if args.id_regex:
        try:
            patterns = [re.compile(args.id_regex)]
        except re.error as exc:
            print(f"错误: --id-regex 无效: {exc}", file=sys.stderr)
            return 2
    else:
        patterns = DEFAULT_PATTERNS

    groups, ungrouped = {}, []
    try:
        for raw in iter_lines(args.files):
            line = raw.rstrip("\r\n")
            sid = extract_id(line, patterns)
            if sid is None:
                ungrouped.append(line)
            else:
                groups.setdefault(sid, []).append(line)
    except OSError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    if args.only and args.only not in groups:
        known = ", ".join(list(groups)[:20]) or "(无)"
        print(f"错误: 未找到会话 {args.only!r}; 现有会话: {known}", file=sys.stderr)
        return 1

    grouped_total = sum(len(v) for v in groups.values())
    print(f"== 会话日志归组 == 会话数: {len(groups)}   归组行: {grouped_total}   未归组行: {len(ungrouped)}")
    ids = [args.only] if args.only else list(groups)
    for sid in ids:
        lines = groups[sid]
        print(f"\n===== 会话 {sid} ({len(lines)} 行) =====")
        if args.summary:
            print(f"  [首行] {lines[0][:80]}")
        else:
            for line in lines:
                print(f"  {line}")
    if not args.only and ungrouped and not args.drop_ungrouped:
        print(f"\n===== 未归组行 ({len(ungrouped)} 行) =====")
        for line in ungrouped:
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
