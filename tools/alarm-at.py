#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定时提醒器 —— 阻塞等待到指定时刻后打印消息并让终端响铃，支持相对时长写法。

用法:
    python alarm-at.py +25m -m "泡面好了"       # 相对时长: 支持 d/h/m/s 组合, 如 +1h30m
    python alarm-at.py 90s                      # 不写 + 也按相对时长处理(纯数字按秒)
    python alarm-at.py 18:00 -m "下班"          # 今天的 18:00 (已过则自动改为明天)
    python alarm-at.py 2026-12-31T23:59:59      # 绝对时刻 (空格或 T 分隔均可)
    python alarm-at.py 2026-12-31               # 未指定时刻, 默认按当天 08:00

选项:
    -m/--message  到点打印的消息 (默认 "时间到!")
    --ring N      响铃次数 (默认 3)
    --no-bell     不响铃

响铃 = 终端 BEL(\\a) + Windows 下追加 winsound.Beep。
退出码: 0 正常到点; 1 目标时刻已过去; 2 参数错误; 130 Ctrl+C 取消。
仅用 Python 标准库。
"""

import argparse
import re
import sys
import time
from datetime import date, datetime, timedelta

DUR_RE = re.compile(r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$", re.I)
REL_RE = re.compile(r"^(?:\d+[dhms])+$|^\d+$", re.I)
CLOCK_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
        raise ValueError(f"无法解析时长: {text!r} (示例: 90s, 25m, 1h30m)")
    d, h, mi, sec = (int(g) if g else 0 for g in m.groups())
    total = d * 86400 + h * 3600 + mi * 60 + sec
    if total <= 0:
        raise ValueError(f"时长必须为正数: {text!r}")
    return float(total)


def parse_when(spec):
    """解析时刻写法，返回 (目标 datetime, 说明文字或 None)。"""
    s = spec.strip()
    if s.startswith("+") or REL_RE.match(s):
        return datetime.now() + timedelta(seconds=parse_duration(s.lstrip("+"))), None
    m = CLOCK_RE.match(s)
    if m:
        hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        now = datetime.now()
        t = now.replace(hour=hh, minute=mm, second=ss, microsecond=0)
        note = None
        if t <= now:
            t += timedelta(days=1)
            note = f"今天的 {hh:02d}:{mm:02d} 已过，自动改为明天"
        return t, note
    if DATE_RE.match(s):
        d = date.fromisoformat(s)  # 范围非法(如 2026-13-40)时抛 ValueError
        return (datetime(d.year, d.month, d.day, 8, 0, 0),
                "未指定时刻，按当天 08:00 计")
    try:
        return datetime.fromisoformat(s), None
    except ValueError:
        raise ValueError(f"无法解析时刻: {spec!r} "
                         f"(示例: +25m, 90s, 18:00, 2026-12-31T23:59:59)")


def human_seconds(sec):
    s = int(sec + 0.5)
    if s < 60:
        return f"{s} 秒"
    m, ss = divmod(s, 60)
    if m < 60:
        return f"{m} 分 {ss} 秒"
    h, mm = divmod(m, 60)
    if h < 48:
        return f"{h} 小时 {mm} 分"
    d, h = divmod(h, 24)
    return f"{d} 天 {h} 小时"


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


def main(argv=None):
    p = argparse.ArgumentParser(description="阻塞到指定时刻，打印消息并终端响铃")
    p.add_argument("when", help="+25m / 90s / 18:00[:SS] / 2026-12-31[ T]HH:MM[:SS] / 2026-12-31")
    p.add_argument("-m", "--message", default="时间到!", help="到点打印的消息")
    p.add_argument("--ring", type=int, default=3, help="响铃次数 (默认 3)")
    p.add_argument("--no-bell", action="store_true", help="不响铃")
    args = p.parse_args(argv)

    try:
        target, note = parse_when(args.when)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2
    remain0 = (target - datetime.now()).total_seconds()
    if remain0 <= 0:
        print(f"错误: 目标时刻 {target:%Y-%m-%d %H:%M:%S} 已过去", file=sys.stderr)
        return 1
    if note:
        print(f"(提示: {note})")
    print(f"提醒已设定: {target:%Y-%m-%d %H:%M:%S} (约 {human_seconds(remain0)} 后)")

    tty = sys.stdout.isatty()
    try:
        while True:
            r = (target - datetime.now()).total_seconds()
            if r <= 0:
                break
            if tty:
                sys.stdout.write(f"\r等待中... 剩余 {r:7.0f} 秒 ")
                sys.stdout.flush()
            time.sleep(min(5.0, r))
    except KeyboardInterrupt:
        print("\n已取消提醒 (Ctrl+C)", file=sys.stderr)
        return 130
    if tty:
        sys.stdout.write("\r" + " " * 40 + "\r")
        sys.stdout.flush()
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {args.message}")
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
