#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""维护窗口推算（maintenance-window）——按周几+时刻的窗口规则推算下一次及未来若干次维护窗口。

用途：
    给定“周几 + 时刻”的周期性维护窗口规则（支持多个周几、每 N 周一轮、
    可选窗口时长），从参考时刻（--from，默认当前时间）向后推算下一次及
    未来若干次维护窗口，输出每次的起止时间与倒计时；只列出严格晚于参考
    时刻的窗口。

示例：
    python maintenance-window.py --rule "wed 03:00" --count 4
    python maintenance-window.py --rule "mon,wed,fri 02:30" --duration-min 90 --count 5
    python maintenance-window.py --rule "周日 23:00" --from "2026-11-02 10:00" --interval-weeks 2

退出码：0 成功；2 参数错误。
"""

import argparse
import datetime as dt
import sys

WEEK_CN = "一二三四五六日"
WEEK_MAP = {}
for _i, _names in enumerate([
        ("mon", "一", "周一", "星期一"),
        ("tue", "二", "周二", "星期二"),
        ("wed", "三", "周三", "星期三"),
        ("thu", "四", "周四", "星期四"),
        ("fri", "五", "周五", "星期五"),
        ("sat", "六", "周六", "星期六"),
        ("sun", "日", "天", "周日", "周天", "星期日", "星期天")]):
    for _n in _names:
        WEEK_MAP[_n.lower()] = _i


def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _rule(s):
    tokens = s.split()
    time_tok = None
    for t in tokens:
        if ":" in t:
            if time_tok is not None:
                raise argparse.ArgumentTypeError("规则中出现多个时刻：%r" % s)
            time_tok = t
    if time_tok is None:
        raise argparse.ArgumentTypeError("规则缺少时刻，格式如 'wed 03:00'")
    try:
        tm = dt.time.fromisoformat(time_tok)
    except ValueError:
        raise argparse.ArgumentTypeError("无效时刻 %r，应为 HH:MM" % time_tok)
    day_part = " ".join(t for t in tokens if t != time_tok)
    days = set()
    for tok in day_part.replace("，", ",").split(","):
        tok = tok.strip().lower()
        if not tok:
            continue
        if tok not in WEEK_MAP:
            raise argparse.ArgumentTypeError(
                "无法识别星期 %r（可用 mon/tue/... 或 一/周一/星期一）" % tok)
        days.add(WEEK_MAP[tok])
    if not days:
        raise argparse.ArgumentTypeError("规则缺少周几，格式如 'wed 03:00'")
    return days, tm


def _from_dt(s):
    try:
        return dt.datetime.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "无效时间 %r，应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM" % s)


def next_windows(ref, days, tm, count, interval_weeks):
    """从 ref 起按日历日推进，收集严格晚于 ref 的前 count 个窗口时刻。"""
    out = []
    d = ref.date()
    limit = 7 * max(interval_weeks, 1) * 80 + 14
    for _ in range(limit):
        if d.weekday() in days:
            w = dt.datetime.combine(d, tm)
            if w > ref and ((d - ref.date()).days // 7) % max(interval_weeks, 1) == 0:
                out.append(w)
                if len(out) >= count:
                    break
        d += dt.timedelta(days=1)
    return out


def main(argv=None):
    _utf8_stdio()
    p = argparse.ArgumentParser(
        description="按周几+时刻的窗口规则推算下一次及未来若干次维护窗口")
    p.add_argument("--rule", required=True,
                   help="窗口规则，如 'wed 03:00'、'mon,wed,fri 02:30'、'周日 23:00'")
    p.add_argument("--from", dest="from_dt", type=_from_dt, default=None,
                   help="参考时刻 YYYY-MM-DD[ HH:MM]（默认当前时间，仅列严格晚于它的窗口）")
    p.add_argument("--count", type=int, default=5, help="推算次数（默认 5）")
    p.add_argument("--duration-min", type=int, default=0,
                   help="窗口时长（分钟，0 表示不显示结束时间）")
    p.add_argument("--interval-weeks", type=int, default=1,
                   help="每 N 周一轮（默认每周，按参考日所在周起算）")
    args = p.parse_args(argv)

    if args.count < 1 or args.interval_weeks < 1 or args.duration_min < 0:
        print("错误：--count 与 --interval-weeks 必须 >= 1，--duration-min 必须 >= 0",
              file=sys.stderr)
        return 2

    try:
        days, tm = _rule(args.rule)
    except argparse.ArgumentTypeError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 2

    ref = args.from_dt or dt.datetime.now().replace(microsecond=0)
    wins = next_windows(ref, days, tm, args.count, args.interval_weeks)
    if not wins:
        print("错误：推算范围内未找到窗口，请检查规则与 --interval-weeks",
              file=sys.stderr)
        return 2

    day_names = "/".join("周" + WEEK_CN[i] for i in sorted(days))
    print("维护窗口规则：%s %s · 每 %d 周一轮 · 参考时刻 %s（仅列严格晚于它的窗口）" %
          (day_names, tm.strftime("%H:%M"), args.interval_weeks,
           ref.strftime("%Y-%m-%d %H:%M")))
    for i, w in enumerate(wins, 1):
        line = "#%d  %s（周%s） %s" % (i, w.strftime("%Y-%m-%d"),
                                      WEEK_CN[w.weekday()], w.strftime("%H:%M"))
        if args.duration_min:
            end = w + dt.timedelta(minutes=args.duration_min)
            line += " ~ " + end.strftime("%H:%M")
        hrs = (w - ref).total_seconds() / 3600.0
        when = ("约 %.0f 小时后" % hrs) if hrs < 48 else ("约 %d 天后" % round(hrs / 24))
        line += "  （%s）" % when
        if i == 1:
            line += "  ← 下一次"
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
