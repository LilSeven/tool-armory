#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""番茄钟计时器：按 25/5 分钟工作-休息循环计时，把完成的番茄数追加到日志文件。

用法:
    python timer-pomodoro.py                                # 25 分工作/5 分休息/4 轮
    python timer-pomodoro.py --work 50 --break 10 --rounds 3
    python timer-pomodoro.py --log C:/Users/me/pomodoro.log # 指定日志文件
    python timer-pomodoro.py --work 0.03 --break 0.02 --rounds 2 --auto
        # 时长单位是分钟、支持小数；--auto 表示阶段间不等待回车（脚本/自测用）

说明:
    每完成一个工作段，就向日志文件追加一行“时间 | 番茄 #N 完成”；
    等待回车时按 Ctrl+C 退出；计时阶段按 Ctrl+C 跳过当前段。
"""

import argparse
import datetime as dt
import sys
import time
from pathlib import Path


def _force_utf8():
    """让中文在管道/重定向（Windows 默认 GBK）下也不乱码。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="番茄钟计时器：工作/休息循环计时并记录完成的番茄数。")
    p.add_argument("--work", type=float, default=25.0,
                   help="单个工作段时长（分钟），默认 25")
    p.add_argument("--break", dest="rest", type=float, default=5.0,
                   help="休息段时长（分钟），默认 5")
    p.add_argument("--rounds", type=int, default=4,
                   help="要完成的番茄个数，默认 4")
    p.add_argument("--log", default=str(Path.home() / "pomodoro.log"),
                   help="番茄完成记录的日志文件（追加写入）")
    p.add_argument("--auto", action="store_true",
                   help="阶段之间不等待回车确认")
    args = p.parse_args(argv)
    if args.work <= 0:
        p.error("--work 必须大于 0")
    if args.rest < 0:
        p.error("--break 不能为负")
    if args.rounds <= 0:
        p.error("--rounds 必须是正整数")
    return args


def append_log(path, idx, work_min):
    """追加一行记录并返回该行内容。"""
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = "%s | 番茄 #%d 完成 | 本次工作 %g 分钟\n" % (stamp, idx, work_min)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)
    return line.rstrip("\n")


def countdown(seconds, label, tty):
    """阻塞倒计时 seconds 秒；tty 时单行刷新，否则只打印开始/结束两行。"""
    end = time.monotonic() + seconds
    if not tty:
        print("  [%s] 开始，时长 %.1f 秒 ..." % (label, seconds))
    while True:
        left = end - time.monotonic()
        if left <= 0:
            break
        m, s = divmod(max(0, int(left)), 60)
        if tty:
            sys.stdout.write("\r  [%s] 剩余 %02d:%02d " % (label, m, s))
            sys.stdout.flush()
        time.sleep(min(0.2, max(0.02, left / 4.0)))
    if tty:
        sys.stdout.write("\r  [%s] 剩余 00:00 \n" % label)
    else:
        print("  [%s] 结束" % label)


def main(argv=None):
    _force_utf8()
    args = parse_args(argv)
    work_sec = args.work * 60.0
    rest_sec = args.rest * 60.0
    tty = sys.stdout.isatty()

    print("番茄钟计划：工作 %g 分钟 -> 休息 %g 分钟，共 %d 个番茄" %
          (args.work, args.rest, args.rounds))
    print("日志文件：%s" % args.log)

    if not args.auto and sys.stdin.isatty():
        try:
            input("按回车开始第一个番茄钟 ...")
        except (EOFError, KeyboardInterrupt):
            print("\n已取消，未记录任何番茄。")
            return 0

    done = 0
    for i in range(1, args.rounds + 1):
        try:
            countdown(work_sec, "工作 %d/%d" % (i, args.rounds), tty)
        except KeyboardInterrupt:
            print("\n  （Ctrl+C：跳过本工作段）")
        done += 1
        try:
            print("  已记录：%s" % append_log(args.log, done, args.work))
        except OSError as exc:
            print("  [警告] 写日志失败：%s" % exc, file=sys.stderr)
        if i == args.rounds:
            break
        try:
            countdown(rest_sec, "休息", tty)
        except KeyboardInterrupt:
            print("\n  （Ctrl+C：跳过休息段）")

    print("\n本次完成番茄：%d 个，日志：%s" % (done, args.log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
