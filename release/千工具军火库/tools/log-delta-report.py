#!/usr/bin/env python3
r"""日志增量报告 (log-delta-report): 与上次快照对比, 报告新增的错误与警告条目。

用途:
    从日志(文件或标准输入)中挑出含错误/警告级别关键字的行 (默认 ERROR, WARN,
    WARNING, FATAL, CRITICAL, 忽略大小写按整词匹配; 可用 --levels 调整), 以
    --snapshot 指定的 JSON 文件为状态库, 记录已见条目的指纹与上一轮次数。
    条目身份 = 去掉行首 PRI/方括号头/时间戳并压缩空白后的文本 —— 同一条错误
    换个时间再打不算新增, 只在次数上升时提示。首次运行(快照不存在)时全部命中
    条目都算新增并建立快照; 每轮结束把本轮计数写回快照, 供下一轮对比。

示例命令:
    python -I log-delta-report.py --snapshot state.json app.log     # 首轮: 全部为新增
    python -I log-delta-report.py --snapshot state.json app.log     # 之后: 只报新增/上升
    python -I log-delta-report.py --snapshot state.json --reset app.log
    python -I log-delta-report.py --snapshot state.json --levels ERROR,FATAL app.log
    cat app.log | python -I log-delta-report.py --snapshot state.json --json

退出码: 0 成功; 2 参数错误或文件读写失败。
"""

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter

DEFAULT_LEVELS = ["ERROR", "WARN", "WARNING", "FATAL", "CRITICAL"]

TS_PREFIX = re.compile(
    r"^\s*(?:"
    r"<\d{1,3}>"                                                                    # syslog PRI
    r"|\[[^\]]*\]"                                                                  # [xxx] 前缀
    r"|\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"   # ISO 时间戳
    r"|[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}"                                 # syslog 时间戳
    r")\s*"
)


class SnapshotError(Exception):
    """快照读取/格式错误。"""


def entry_key(line):
    """条目身份: 去掉行首 PRI/方括号头/时间戳, 再压缩空白。"""
    s = line.strip()
    mobj = TS_PREFIX.match(s)
    if mobj:
        s = s[mobj.end():].lstrip()
    return re.sub(r"\s+", " ", s)


def fingerprint(key):
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def entry_count(rec):
    if isinstance(rec, dict):
        return int(rec.get("count", 0))
    if isinstance(rec, int):
        return rec
    return 0


def load_snapshot(path):
    """返回 (entries, 是否已存在); 快照损坏或格式不对抛 SnapshotError。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}, False
    except (OSError, ValueError) as exc:  # JSONDecodeError 是 ValueError 子类
        raise SnapshotError(f"读取快照失败: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("entries"), dict):
        raise SnapshotError(f"快照格式不符 (缺少 entries 对象): {path}")
    return data["entries"], True


def save_snapshot(path, entries):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "entries": entries}, fh,
                  ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)


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
        prog="log-delta-report",
        description="与上次快照对比, 报告新增的错误与警告条目。")
    parser.add_argument("files", nargs="*", help="日志文件; 缺省读标准输入")
    parser.add_argument("--snapshot", required=True, metavar="FILE",
                        help="快照 JSON 文件 (必需; 不存在则视为首轮, 全部算新增)")
    parser.add_argument("--levels", default=",".join(DEFAULT_LEVELS), metavar="L1,L2",
                        help="级别关键字, 逗号分隔 (默认 ERROR,WARN,WARNING,FATAL,CRITICAL)")
    parser.add_argument("--reset", action="store_true",
                        help="忽略已有快照内容, 本轮全部视为新增并重写快照")
    parser.add_argument("--json", action="store_true", dest="as_json", help="以 JSON 输出报告")
    args = parser.parse_args(argv)

    levels = [lv.strip() for lv in args.levels.split(",") if lv.strip()]
    if not levels:
        print("错误: --levels 不能为空", file=sys.stderr)
        return 2
    try:
        level_rx = re.compile(r"\b(?:" + "|".join(re.escape(lv) for lv in levels) + r")\b", re.I)
    except re.error as exc:
        print(f"错误: --levels 无法编译为正则: {exc}", file=sys.stderr)
        return 2

    try:
        old, existed = ({}, False) if args.reset else load_snapshot(args.snapshot)
    except SnapshotError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    total, matched = 0, []
    try:
        for raw in iter_lines(args.files):
            line = raw.rstrip("\r\n")
            total += 1
            if level_rx.search(line):
                matched.append((line, fingerprint(entry_key(line))))
    except OSError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    current = Counter(fp for _, fp in matched)
    sample = {}
    for line, fp in matched:
        sample.setdefault(fp, line)

    new_fps = [fp for fp in current if fp not in old]
    ups = [(fp, entry_count(old[fp]), current[fp])
           for fp in current if fp in old and current[fp] > entry_count(old[fp])]

    if args.as_json:
        print(json.dumps({
            "total_lines": total,
            "matched_lines": len(matched),
            "new": [{"count": current[fp], "entry": sample[fp]} for fp in new_fps],
            "updated": [{"from": before, "to": after, "entry": sample[fp]}
                        for fp, before, after in ups],
        }, ensure_ascii=False, indent=2))
    else:
        print("== 日志增量报告 ==")
        print(f"输入: {total} 行, 命中错误/警告 {len(matched)} 行, 合计 {len(current)} 类条目")
        if existed and not args.reset:
            print(f"快照: {args.snapshot} (已见 {len(old)} 类)")
        else:
            print(f"快照: {args.snapshot} ({'--reset 重建' if args.reset else '新建'})")
        if new_fps:
            print(f"\n新增条目 ({len(new_fps)} 类):")
            for fp in new_fps:
                print(f"  [新增] x{current[fp]:<4} {sample[fp][:140]}")
        else:
            print("\n本次无新增错误/警告条目。")
        if ups:
            print(f"\n已知条目次数上升 ({len(ups)} 类):")
            for fp, before, after in ups:
                print(f"  [上升] x{before} -> x{after}  {sample[fp][:140]}")

    merged = {fp: {"count": entry_count(rec), "sample": str(rec.get("sample", ""))[:200]}
              for fp, rec in old.items() if isinstance(rec, dict)}
    for fp in current:
        merged[fp] = {"count": current[fp], "sample": sample[fp][:200]}
    try:
        save_snapshot(args.snapshot, merged)
    except OSError as exc:
        print(f"错误: 写入快照失败: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
