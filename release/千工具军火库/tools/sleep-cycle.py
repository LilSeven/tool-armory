#!/usr/bin/env python3
"""睡眠周期推荐 —— 按 90 分钟睡眠周期推荐最佳就寝或起床时刻。

人类睡眠以约 90 分钟为一个周期，在周期结束节点醒来更清醒。
给定目标起床时刻，本工具倒推若干个完整睡眠周期（并预留入睡时间），
给出推荐就寝时刻；或给定就寝时刻，正向推荐起床时刻。

用法示例:
    python sleep-cycle.py --wake 07:00                # 目标 07:00 起床 -> 推荐就寝
    python sleep-cycle.py --bed 23:30                 # 23:30 就寝 -> 推荐起床
    python sleep-cycle.py --wake 07:00 --latency 5    # 自定义入睡耗时（分钟）
    python sleep-cycle.py --bed 23:30 --cycles 6      # 只看 6 个周期的结果
"""

import argparse
import sys

CYCLE_MIN = 90          # 单个睡眠周期时长（分钟）
DEFAULT_LATENCY = 15    # 默认预留的入睡时间（分钟）
DEFAULT_CYCLES = (6, 5, 4, 3)


def _force_utf8_stdio():
    """让输出在 Windows 管道/重定向下也按 UTF-8 编码（Git Bash 友好）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_hhmm(text):
    """解析 HH:MM 为当日内分钟数（0..1439）。"""
    parts = text.split(":")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("时间格式应为 HH:MM，收到 %r" % text)
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        raise argparse.ArgumentTypeError("时间格式应为 HH:MM，收到 %r" % text)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise argparse.ArgumentTypeError("时间超出 00:00-23:59 范围: %r" % text)
    return hour * 60 + minute


def fmt_clock(minutes):
    """把（可能跨日溢出的）分钟数格式化为 HH:MM。"""
    minutes %= 24 * 60
    return "%02d:%02d" % divmod(minutes, 60)


def main(argv=None):
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="按 90 分钟睡眠周期推荐最佳就寝或起床时刻")
    parser.add_argument("--wake", type=parse_hhmm, metavar="HH:MM",
                        help="目标起床时刻（与 --bed 二选一）")
    parser.add_argument("--bed", type=parse_hhmm, metavar="HH:MM",
                        help="就寝时刻（与 --wake 二选一）")
    parser.add_argument("--latency", type=int, default=DEFAULT_LATENCY, metavar="MIN",
                        help="入睡耗时（分钟，默认 %d）" % DEFAULT_LATENCY)
    parser.add_argument("--cycles", type=int, choices=DEFAULT_CYCLES, metavar="N",
                        help="只显示 N 个周期的结果（可选: %s）"
                             % "/".join(str(c) for c in DEFAULT_CYCLES))
    args = parser.parse_args(argv)

    if (args.wake is None) == (args.bed is None):
        parser.error("必须且只能提供 --wake 或 --bed 之一")
    if not 0 <= args.latency <= 240:
        parser.error("--latency 应在 0-240 分钟之间")

    cycles_list = [args.cycles] if args.cycles else list(DEFAULT_CYCLES)
    if args.wake is not None:
        print("目标起床 %s，预留入睡 %d 分钟:" % (fmt_clock(args.wake), args.latency))
        for c in sorted(cycles_list, reverse=True):
            raw = args.wake - args.latency - c * CYCLE_MIN
            marker = "（前一晚）" if raw < 0 else ""
            print("  %d 个周期（%d 小时 %02d 分）: %s 就寝%s"
                  % (c, c * CYCLE_MIN // 60, c * CYCLE_MIN % 60,
                     fmt_clock(raw), marker))
    else:
        print("就寝 %s，预留入睡 %d 分钟:" % (fmt_clock(args.bed), args.latency))
        for c in sorted(cycles_list):
            raw = args.bed + args.latency + c * CYCLE_MIN
            marker = "（次日）" if raw >= 24 * 60 else ""
            print("  %d 个周期（%d 小时 %02d 分）: %s 起床%s"
                  % (c, c * CYCLE_MIN // 60, c * CYCLE_MIN % 60,
                     fmt_clock(raw), marker))
    return 0


if __name__ == "__main__":
    sys.exit(main())
