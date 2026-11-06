#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实时倒计时器 —— 终端实时刷新显示距目标时刻剩余的天/时/分/秒，到点打印消息并终端响铃。

用法:
    python countdown-live.py 2026-12-31T23:59:59   # 绝对时刻 (空格或 T 分隔均可)
    python countdown-live.py 2026-12-31            # 目标日 00:00
    python countdown-live.py 18:00                 # 今天(若已过则明天)的 18:00
    python countdown-live.py +2m30s                # 2 分 30 秒后 (支持 d/h/m/s 组合)
    python countdown-live.py +10s -m 冲刺结束 --no-bell

说明:
    终端下用 \\r 原地刷新；输出被重定向时每秒仅打印一行状态，避免刷屏。
    响铃 = 终端 BEL(\\a) + Windows 下追加 winsound.Beep。

退出码: 0 倒计时正常结束; 1 目标时刻已过去; 2 参数错误; 130 Ctrl+C 中断。
仅用 Python 标准库。
"""

import argparse
import re
import sys
import time
from datetime import datetime, timedelta

DUR_RE = re.compile(r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$", re.I)
REL_RE = re.compile(r"^(?:\d+[dhms])+$|^\d+$", re.I)
CLOCK_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def parse_duration(text):
    """解析时长字符串(如 90s / 5m / 1h30m / 2d)为秒数，失败抛 ValueError。"""
    s = text.strip()
    if s.isdigit():
        n = float(s)
        if n <= 0:
            raise ValueError(f"时长必须为正数: {text!r}")
        return n
    m = DUR_RE.match(s)
    if not m:
        raise ValueError(f"无法解析时长: {text!r} (示例: 90s, 5m, 1h30m, 2d)")
    d, h, mi, sec = (int(g) if g else 0 for g in m.groups())
    total = d * 86400 + h * 3600 + mi * 60 + sec
    if total <= 0:
        raise ValueError(f"时长必须为正数: {text!r}")
    return float(total)


def parse_target(spec):
    """把目标时刻写法解析为 datetime。"""
    s = spec.strip()
    now = datetime.now()
    if s.startswith("+") or REL_RE.match(s):
        return now + timedelta(seconds=parse_duration(s.lstrip("+")))
    m = CLOCK_RE.match(s)
    if m:
        hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        t = now.replace(hour=hh, minute=mm, second=ss, microsecond=0)
        if t <= now:
            t += timedelta(days=1)
        return t
    try:
        return datetime.fromisoformat(s)  # YYYY-MM-DD[ T]HH:MM[:SS]
    except ValueError:
        raise ValueError(f"无法解析目标时刻: {spec!r} "
                         f"(示例: 2026-12-31T23:59:59, 18:00, +5m)")


def ring(times):
    """响铃：终端 BEL，Windows 下再叠加 winsound.Beep。"""
    for _ in range(max(1, times)):
        sys.stdout.write("\a")
        sys.stdout.flush()
        try:
            import winsound
            winsound.Beep(880, 250)
        except Exception:
            time.sleep(0.3)


def fmt_remaining(remain):
    total = max(0, int(remain))
    d, rem = divmod(total, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    return f"{d}天 {h:02d}:{m:02d}:{s:02d}" if d else f"{h:02d}:{m:02d}:{s:02d}"


def main(argv=None):
    p = argparse.ArgumentParser(description="终端实时倒计时到指定时刻，到点响铃")
    p.add_argument("target", help="目标时刻: 2026-12-31T23:59:59 / 18:00 / +2m30s")
    p.add_argument("-m", "--message", default="时间到!", help="到点后打印的消息")
    p.add_argument("--no-bell", action="store_true", help="到点后不响铃")
    p.add_argument("--ring", type=int, default=3, help="响铃次数 (默认 3)")
    p.add_argument("--interval", type=float, default=0.25, help="刷新间隔秒 (默认 0.25)")
    args = p.parse_args(argv)

    try:
        target = parse_target(args.target)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2
    remain0 = (target - datetime.now()).total_seconds()
    if remain0 <= 0:
        print(f"错误: 目标时刻 {target:%Y-%m-%d %H:%M:%S} 已过去", file=sys.stderr)
        return 1
    print(f"目标时刻: {target:%Y-%m-%d %H:%M:%S} (剩余 {fmt_remaining(remain0)})")

    tty = sys.stdout.isatty()
    last = None
    try:
        while True:
            remain = (target - datetime.now()).total_seconds()
            if remain <= 0:
                break
            line = f"剩余 {fmt_remaining(remain)}  →  {target:%Y-%m-%d %H:%M:%S}"
            if tty:
                sys.stdout.write("\r" + line + "  ")
                sys.stdout.flush()
            elif line != last:  # 重定向时一行/秒，不刷屏
                sys.stdout.write(line + "\n")
                sys.stdout.flush()
                last = line
            time.sleep(min(args.interval, remain))
    except KeyboardInterrupt:
        print("\n已取消倒计时 (Ctrl+C)", file=sys.stderr)
        return 130
    if tty:
        sys.stdout.write("\r" + " " * 60 + "\r")
        sys.stdout.flush()
    print(f"{args.message}  ({target:%Y-%m-%d %H:%M:%S})")
    if not args.no_bell:
        try:
            ring(args.ring)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
