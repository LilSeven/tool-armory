#!/usr/bin/env python3
r"""噪音行过滤 (log-noise-filter): 统计高频重复行视为噪音并过滤, 突出显示低频的异常日志。

用途:
    读入日志(文件或标准输入)后, 将每行归一化 —— 时间戳/IP/UUID/长十六进制串/数字
    分别替换为 <TS>/<IP>/<UUID>/<HEX>/<N> 占位符 (--raw 可关闭归一化) —— 再统计
    各模式出现次数; 次数达到阈值的模式判为噪音, 从主输出中过滤并单独给出噪音榜单;
    其余低频行按原顺序完整输出, 即需要人工关注的疑似异常日志。输入整体载入内存。

示例命令:
    python -I log-noise-filter.py --threshold 10 app.log
    python -I log-noise-filter.py --show-noise --top 5 app.log
    python -I log-noise-filter.py --raw mixed.log
    cat mixed.log | python -I log-noise-filter.py

退出码: 0 成功; 2 参数错误或文件读取失败。
"""

import argparse
import math
import re
import sys
from collections import Counter

NORM_PATTERNS = [
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"), "<TS>"),
    (re.compile(r"\b[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\b"), "<TS>"),
    (re.compile(r"\b\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b"), "<TS>"),
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<UUID>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b"), "<IP>"),
    (re.compile(r"\b[0-9a-fA-F]{8,}\b"), "<HEX>"),
    (re.compile(r"\d+"), "<N>"),
]


def normalize(line):
    """把时间戳/IP/UUID/HEX/数字归一化为占位符, 使同类行折叠为一个模式。"""
    s = line.strip()
    for rx, repl in NORM_PATTERNS:
        s = rx.sub(repl, s)
    return s


def auto_threshold(total):
    """缺省阈值: max(5, 总行数的 2%)。"""
    return max(5, math.ceil(total * 0.02))


def ratio(part, total):
    return f"{(part / total * 100):.1f}%" if total else "0.0%"


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
        prog="log-noise-filter",
        description="统计高频重复行视为噪音并过滤, 突出显示低频的异常日志。")
    parser.add_argument("files", nargs="*", help="日志文件; 缺省读标准输入")
    parser.add_argument("--threshold", type=int, default=None, metavar="N",
                        help="出现 >= N 次的模式视为噪音; 缺省 auto (>=max(5, 总行数的2%%))")
    parser.add_argument("--top", type=int, default=10, metavar="N",
                        help="噪音榜单最多显示 N 条 (默认 10, <=0 不限)")
    parser.add_argument("--show-noise", action="store_true",
                        help="额外列出被判为噪音的行 (标注出现次数)")
    parser.add_argument("--raw", action="store_true", help="不做归一化, 按整行精确计数")
    args = parser.parse_args(argv)

    entries, counts, first_seen = [], Counter(), {}
    try:
        for raw in iter_lines(args.files):
            line = raw.rstrip("\r\n")
            key = line if args.raw else normalize(line)
            entries.append((line, key))
            counts[key] += 1
            first_seen.setdefault(key, line)
    except OSError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2

    total = len(entries)
    threshold = args.threshold if args.threshold is not None else auto_threshold(total)
    noise_keys = {k for k, c in counts.items() if c >= threshold}
    noise_lines = sum(counts[k] for k in noise_keys)
    keep = total - noise_lines

    print("== 噪音过滤报告 ==")
    print(f"输入行数: {total}   唯一模式: {len(counts)}   阈值: >= {threshold} 次"
          + ("" if args.threshold is not None else " (auto)"))
    print(f"噪音行: {noise_lines} ({ratio(noise_lines, total)})   "
          f"保留的低频/异常行: {keep} ({ratio(keep, total)})")

    top = sorted(noise_keys, key=lambda k: (-counts[k], first_seen[k]))
    if args.top > 0:
        top = top[: args.top]
    if top:
        print(f"\n-- 噪音模式 TOP {len(top)} --")
        for key in top:
            print(f"  x{counts[key]:<6} {ratio(counts[key], total):>7}  代表行: {first_seen[key][:100]}")
    else:
        print("\n(未发现达到阈值的噪音模式)")

    if args.show_noise and noise_keys:
        print("\n-- 噪音行明细 --")
        for line, key in entries:
            if key in noise_keys:
                print(f"  [噪音 x{counts[key]}] {line}")

    print(f"\n-- 保留的低频/异常行 ({keep} 行, 原顺序) --")
    if keep == 0:
        print("  (无)")
    for line, key in entries:
        if key not in noise_keys:
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
