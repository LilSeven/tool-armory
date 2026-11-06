#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自然语言日期解析（natural-parse）：解析"明天下午3点""下周五""三天后"等中文相对日期表达为具体时刻。

支持：今天/明天/后天/大后天/昨天/前天、N天(周/月/年/小时/分钟)后/前（数字或简体中文数字如"三天后"）、
（下/上/下下/上上/本）周X|星期X|礼拜X、X月X日(号)（可带年份）、
凌晨/早上/上午/中午/下午/傍晚/晚上 + X点(半/一刻/三刻/X分)、HH:MM。

用法:
  python natural-parse.py "明天下午3点"
  python natural-parse.py "三天后" "下周五" "昨天早上8点半"    # 可传多个表达式
  python natural-parse.py "下周三晚上十点一刻" --now "2026-11-02 12:00"
示例:
  python natural-parse.py "明天下午3点"   ->  <明天日期> 15:00:00（星期X）
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timedelta

CN_DIG = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9}
WEEK = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}

# 表达式归一化：把"明晚"等合写词拆成 日期+时段
NORMALIZE = {"今晚": "今天晚上", "明晚": "明天晚上", "昨晚": "昨天晚上",
             "明早": "明天早上", "明晨": "明天早上"}

TIME_RE = re.compile(
    r"(凌晨|清晨|早上|上午|中午|午后|下午|傍晚|晚上|夜里|半夜|晚)"
    r"\s*(?P<hour>\d{1,2}|[一二两三四五六七八九十]+)\s*[点时]\s*"
    r"(?:(?P<min>\d{1,2}|[一二三四五六十]+)(?!刻)\s*分?|(?P<half>半)|(?P<quarter>一刻|三刻))?"
)
CLOCK_RE = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)")
NUM = r"(?:\d{1,3}|[一二两三四五六七八九十]+)"

BARE_DAYS = {"今天": 0, "今日": 0, "明天": 1, "明日": 1, "后天": 2,
             "大后天": 3, "昨天": -1, "昨日": -1, "前天": -2}
PERIOD_PM = {"中午", "午后", "下午", "傍晚", "晚上", "夜里", "晚"}


def cn2int(s: str) -> int:
    """解析简中文数字（支持 十/十五/二十一/两 等，最大 99）。"""
    s = s.strip()
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    if "十" in s:
        left, _, right = s.partition("十")
        if (left and left not in CN_DIG) or (right and right not in CN_DIG):
            raise ValueError(f"无法解析数字: {s!r}")
        tens = CN_DIG.get(left, 1) if left else 1
        ones = CN_DIG.get(right, 0) if right else 0
        return tens * 10 + ones
    if s in CN_DIG:
        return CN_DIG[s]
    raise ValueError(f"无法解析数字: {s!r}")


def add_months(d: date, n: int) -> date:
    """在 d 上加减 n 个月，超出月末时收敛到月末（1月31日 + 1月 = 2月28日）。"""
    y, m = d.year, d.month - 1 + n
    y += m // 12
    m = m % 12 + 1
    for day in range(d.day, 0, -1):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    raise ValueError("月份运算失败")


def parse_date_part(t: str, today: date):
    """解析去掉时间部分后的日期子串，返回 date；无法识别返回 None。"""
    t = t.replace("的", "").strip()
    if not t:
        return today
    if t in BARE_DAYS:
        return today + timedelta(days=BARE_DAYS[t])
    m = re.fullmatch(rf"(?:(\d{{4}})年)?({NUM})月({NUM})[日号]", t)
    if m:
        year = int(m.group(1)) if m.group(1) else today.year
        return date(year, cn2int(m.group(2)), cn2int(m.group(3)))
    m = re.fullmatch(r"(下下|上上|下|上|本|这)?(?:个)?(?:周|星期|礼拜)([一二三四五六日天])", t)
    if m:
        weeks = {"下下": 2, "上上": -2, "下": 1, "上": -1, "本": 0,
                 "这": 0, None: 0}[m.group(1)]
        monday = today - timedelta(days=today.weekday())
        return monday + timedelta(weeks=weeks, days=WEEK[m.group(2)])
    if t in ("下周", "下星期", "下礼拜"):
        return today + timedelta(days=7)
    if t in ("下下周", "下下星期", "下下礼拜"):
        return today + timedelta(days=14)
    if t in ("上周", "上星期", "上礼拜"):
        return today - timedelta(days=7)
    m = re.fullmatch(rf"({NUM})\s*个?\s*天(后|前|之后|之前)", t)
    if m:
        n = cn2int(m.group(1))
        return today + timedelta(days=n if "后" in m.group(2) else -n)
    m = re.fullmatch(rf"({NUM})\s*个?\s*(?:星期|周|礼拜)(后|前|之后|之前)", t)
    if m:
        n = cn2int(m.group(1))
        return today + timedelta(weeks=n if "后" in m.group(2) else -n)
    m = re.fullmatch(rf"({NUM})\s*个?月(后|前|之后|之前)", t)
    if m:
        n = cn2int(m.group(1))
        return add_months(today, n if "后" in m.group(2) else -n)
    m = re.fullmatch(rf"({NUM})\s*年(后|前|之后|之前)", t)
    if m:
        n = cn2int(m.group(1))
        return date(today.year + (n if "后" in m.group(2) else -n),
                    today.month, today.day)
    return None


def parse_expr(expr: str, now: datetime) -> datetime:
    """把一条中文相对日期表达解析为具体时刻（datetime）。"""
    s = expr.strip()
    for a, b in NORMALIZE.items():
        s = s.replace(a, b)
    hour = minute = None
    period = None
    have_time = False
    rest = s
    m = TIME_RE.search(s)
    if m:
        period = m.group(1)
        hour = cn2int(m.group("hour"))
        if m.group("half"):
            minute = 30
        elif m.group("quarter"):
            minute = 15 if m.group("quarter") == "一刻" else 45
        elif m.group("min"):
            minute = cn2int(m.group("min"))
        rest = s[:m.start()] + s[m.end():]
    else:
        m2 = CLOCK_RE.search(s)
        if m2:
            hour, minute = int(m2.group(1)), int(m2.group(2))
            rest = s[:m2.start()] + s[m2.end():]
    if hour is not None:
        have_time = True
    if hour is None:
        hour, minute = 0, 0

    if period == "半夜" and hour == 12:
        hour = 0
    if period == "凌晨" and hour == 12:
        hour = 0
    if period in PERIOD_PM and hour < 12:
        hour += 12
    if not (0 <= hour <= 23) or not (0 <= (minute or 0) <= 59):
        raise ValueError(f"时间部分不合理: {expr!r}")

    d = parse_date_part(rest, now.date())
    if d is not None:
        return datetime(d.year, d.month, d.day, hour, minute or 0)

    # 日期部分是"N小时/分钟后(前)"这类时长表达：在基准时刻上平移
    t = rest.replace("的", "").strip()
    m3 = re.fullmatch(rf"({NUM}|半)\s*个?\s*(小时|钟头|分钟|分)(后|前|之后|之前)", t)
    if m3:
        n = 0.5 if m3.group(1) == "半" else cn2int(m3.group(1))
        delta = timedelta(minutes=n * 60) if m3.group(2) in ("小时", "钟头") \
            else timedelta(minutes=n)
        if "前" in m3.group(3):
            delta = -delta
        if have_time:
            base = datetime(now.year, now.month, now.day, hour, minute or 0)
        else:
            base = now.replace(second=0, microsecond=0)
        return base + delta
    raise ValueError(f"无法识别的日期部分: {rest.strip()!r}（来自 {expr!r}）")


WEEK_CN = "一二三四五六日"


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(
        description="自然语言日期解析：把\"明天下午3点\"\"下周五\"\"三天后\"等中文相对表达解析为具体时刻。")
    ap.add_argument("exprs", nargs="+", help="一个或多个中文日期表达")
    ap.add_argument("--now", help="基准时刻，格式 YYYY-MM-DD[ HH:MM]（默认当前时间）")
    args = ap.parse_args(argv)

    if args.now:
        try:
            now = datetime.strptime(args.now.strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                now = datetime.strptime(args.now.strip(), "%Y-%m-%d %H:%M")
            except ValueError:
                try:
                    now = datetime.strptime(args.now.strip(), "%Y-%m-%d")
                except ValueError:
                    print(f"错误：--now 需为 YYYY-MM-DD[ HH:MM] 格式，收到 {args.now!r}",
                          file=sys.stderr)
                    return 2
    else:
        now = datetime.now()

    rc = 0
    for expr in args.exprs:
        try:
            dt = parse_expr(expr, now)
        except ValueError as exc:
            print(f"{expr} -> 错误：{exc}", file=sys.stderr)
            rc = 1
            continue
        wd = "星期" + WEEK_CN[dt.weekday()]
        delta = (dt.date() - now.date()).days
        print(f"{expr} -> {dt.strftime('%Y-%m-%d %H:%M:%S')}（{wd}，相对今天 {delta:+d} 天）")
    return rc


if __name__ == "__main__":
    sys.exit(main())
