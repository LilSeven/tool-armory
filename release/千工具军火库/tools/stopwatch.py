#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命令行秒表：开始/暂停/计圈/重置的交互式秒表，圈次与总时长精确到毫秒。

用法:
    python stopwatch.py                     # 交互模式，逐条输入命令
    printf 's\\nl\\np\\nq\\n' | python -I stopwatch.py   # 用管道喂命令（自测）

命令（不区分大小写）:
    s / start   开始或继续        p / pause   暂停
    l / lap     记一圈            r / reset   归零重来
    空行 / d    显示当前状态      q / quit    退出并打印汇总

时间基准为 time.monotonic()（不受修改系统时间影响），显示精度毫秒。
"""

import sys
import time


def _force_utf8():
    """让中文在管道/重定向（Windows 默认 GBK）下也不乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def fmt(seconds):
    """秒 -> HH:MM:SS.mmm"""
    ms = int(round(seconds * 1000.0))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return "%02d:%02d:%02d.%03d" % (h, m, s, ms)


class Stopwatch:
    """累计型秒表：暂停时把已走时间累加进 _acc。"""

    def __init__(self):
        self._acc = 0.0
        self._start = None          # 最近一次 start 的 time.monotonic() 值
        self.laps = []              # [(圈号, 单圈秒, 累计秒), ...]

    @property
    def running(self):
        return self._start is not None

    def elapsed(self):
        if self._start is None:
            return self._acc
        return self._acc + (time.monotonic() - self._start)

    def start(self):
        if self.running:
            return "已经在计时中了"
        self._start = time.monotonic()
        return None

    def pause(self):
        if not self.running:
            return "当前没有在计时"
        self._acc += time.monotonic() - self._start
        self._start = None
        return None

    def lap(self):
        if not self.running:
            return "请先 start 再计圈"
        total = self.elapsed()
        prev = self.laps[-1][2] if self.laps else 0.0
        rec = (len(self.laps) + 1, total - prev, total)
        self.laps.append(rec)
        return rec

    def reset(self):
        self._acc = 0.0
        self._start = None
        self.laps = []


MENU = "命令：s=开始/继续  p=暂停  l=计圈  r=重置  空行=状态  q=退出"


def main(argv=None):
    _force_utf8()
    sw = Stopwatch()
    print("命令行秒表（精度毫秒，基于 time.monotonic）")
    print(MENU)
    while True:
        try:
            cmd = input("秒表> ").strip().lower()
        except EOFError:
            cmd = "q"
        except KeyboardInterrupt:
            cmd = "q"
        if cmd in ("", "d", "status"):
            print("  状态：%s  累计 %s  已计圈 %d" %
                  ("计时中" if sw.running else "暂停/未启动",
                   fmt(sw.elapsed()), len(sw.laps)))
        elif cmd in ("s", "start"):
            err = sw.start()
            print("  开始计时！" if err is None else "  " + err)
        elif cmd in ("p", "pause"):
            err = sw.pause()
            if err is None:
                print("  已暂停，累计 %s" % fmt(sw.elapsed()))
            else:
                print("  " + err)
        elif cmd in ("l", "lap"):
            res = sw.lap()
            if isinstance(res, tuple):
                n, split, total = res
                print("  圈 %d：单圈 %s | 累计 %s" % (n, fmt(split), fmt(total)))
            else:
                print("  " + res)
        elif cmd in ("r", "reset"):
            sw.reset()
            print("  已重置归零。")
        elif cmd in ("q", "quit", "exit"):
            break
        else:
            print("  未知命令。%s" % MENU)

    print("\n汇总：总时长 %s，共 %d 圈" % (fmt(sw.elapsed()), len(sw.laps)))
    for n, split, total in sw.laps:
        print("  圈 %d：单圈 %s | 累计 %s" % (n, fmt(split), fmt(total)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
