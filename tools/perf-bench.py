#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""计时基准测试：用 time.perf_counter 对比多种计时函数的分辨率与调用开销，
演示 time.time 与 time.perf_counter 等时钟的精度差异。

内容:
    1) 声明分辨率: time.get_clock_info(name).resolution
    2) 实测最小增量: 连续调用相邻两次读数的最小正差值
    3) 调用开销: 空转 N 次的平均每次耗时（用 perf_counter 度量）
    4) 演示: 各时钟测量同一次 time.sleep(0.05) 的走时

用法:
    python perf-bench.py                                   # 默认 200000 次调用
    python perf-bench.py --calls 20000 --budget 0.05       # 快速自测
    python perf-bench.py --no-sleep                        # 跳过 sleep 演示
"""

import argparse
import sys
import time


def _force_utf8():
    """让中文在管道/重定向（Windows 默认 GBK）下也不乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# (名称, 函数, 读数 -> 秒 的换算系数)
CLOCKS = [
    ("time.time", time.time, 1.0),
    ("time.time_ns", time.time_ns, 1e-9),
    ("time.monotonic", time.monotonic, 1.0),
    ("time.monotonic_ns", time.monotonic_ns, 1e-9),
    ("time.perf_counter", time.perf_counter, 1.0),
    ("time.perf_counter_ns", time.perf_counter_ns, 1e-9),
    ("time.process_time", time.process_time, 1.0),
    ("time.process_time_ns", time.process_time_ns, 1e-9),
    ("time.thread_time", getattr(time, "thread_time", None), 1.0),
]


def fmt_dur(sec):
    if sec is None:
        return "n/a"
    if sec >= 1.0:
        return "%.3g s" % sec
    if sec >= 1e-3:
        return "%.3g ms" % (sec * 1e3)
    if sec >= 1e-6:
        return "%.3g us" % (sec * 1e6)
    return "%.3g ns" % (sec * 1e9)


def clock_info(name):
    base = name[5:] if name.startswith("time.") else name   # 去 "time." 前缀
    if base.endswith("_ns"):
        base = base[:-3]                                    # _ns 是同一时钟
    try:
        info = time.get_clock_info(base)
        return info.resolution, bool(info.monotonic), bool(info.adjustable)
    except (ValueError, AttributeError):
        return None, None, None


def overhead_ns(fn, calls):
    """空转 calls 次求平均单次调用开销（ns/次），用 perf_counter 度量。"""
    for _ in range(1000):           # 预热
        fn()
    t0 = time.perf_counter()
    for _ in range(calls):
        fn()
    t1 = time.perf_counter()
    return (t1 - t0) / calls * 1e9


def min_delta(fn, scale, budget):
    """在 budget 秒预算内连续调用，返回最小正增量（换算成秒）。"""
    best = None
    prev = fn()
    deadline = time.perf_counter() + budget
    while time.perf_counter() < deadline:
        cur = fn()
        d = (cur - prev) * scale
        if d > 0.0 and (best is None or d < best):
            best = d
            if best <= 2e-8:        # 已到 20ns 量级，无需继续找
                break
        prev = cur
    return best


def sleep_probe(fn, scale, seconds=0.05):
    """用某时钟测量同一次 time.sleep 的走时。"""
    t0 = fn()
    time.sleep(seconds)
    t1 = fn()
    return (t1 - t0) * scale


def main(argv=None):
    _force_utf8()
    p = argparse.ArgumentParser(
        description="对比 Python 各计时函数的分辨率、单调性与调用开销")
    p.add_argument("--calls", type=int, default=200000,
                   help="测调用开销时每个函数空转次数，默认 200000")
    p.add_argument("--budget", type=float, default=0.2,
                   help="测最小增量时每个函数的时间预算（秒），默认 0.2")
    p.add_argument("--no-sleep", action="store_true", help="跳过 sleep 演示")
    args = p.parse_args(argv)
    if args.calls <= 0 or args.budget <= 0:
        p.error("--calls/--budget 必须为正数")

    print("本机时钟对比（%s, Python %d.%d.%d）" %
          (sys.platform, sys.version_info[0], sys.version_info[1],
           sys.version_info[2]))
    print("=== 1) 分辨率与调用开销 ===")
    print("%-22s %10s %12s %5s %5s %14s" %
          ("clock", "declared", "min-delta", "mono", "adj", "ns/call"))
    for name, fn, scale in CLOCKS:
        if fn is None:
            print("%-22s %10s %12s %5s %5s %14s" %
                  (name, "-", "-", "-", "-", "不支持"))
            continue
        res, mono, adj = clock_info(name)
        md = min_delta(fn, scale, args.budget)
        ov = overhead_ns(fn, args.calls)
        print("%-22s %10s %12s %5s %5s %14.1f" %
              (name,
               "-" if res is None else fmt_dur(res),
               fmt_dur(md),
               "-" if mono is None else ("Y" if mono else "N"),
               "-" if adj is None else ("Y" if adj else "N"),
               ov))

    if not args.no_sleep:
        print("\n=== 2) 演示：各时钟测量同一次 time.sleep(0.05) ===")
        for name, fn, scale in CLOCKS:
            if fn is None:
                continue
            print("  %-22s 测得 %.6f s" % (name, sleep_probe(fn, scale)))
        print("  （CPU 类时钟 process_time/thread_time 不计入睡眠；"
              "wall 类时钟受各自分辨率影响，读数会量化到步长）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
