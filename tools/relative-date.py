#!/usr/bin/env python3
"""相对日期表达生成 —— 把日期翻译为“3 天前”“下下周二”“月底”等自然语言相对表达。

用法:
    python relative-date.py <日期> [--base <基准日期>]

示例命令:
    python relative-date.py 2026-11-24 --base 2026-11-10    # → 2 周后 / 下下周二
    python relative-date.py 2026-11-30 --base 2026-11-10    # → 20 天后 / 本月底
    python relative-date.py 2026-10-30                       # 基准默认为今天

输出（以基准日为参照，列出所有适用的表达）:
    * 天数：今天/明天/后天/大后天/昨天/前天/大前天，或 N 天后/N 天前
    * 周数：恰好为整周差时给 N 周后/N 周前
    * 星期：相差 ±2 周内给 本周X/下周X/下下周X/上周X/上上周X（周一为一周之首）
    * 月初/月底：日期为当月 1 号或最后一天时给 上/本/下 月初·月底
    * 月数：与基准“同日”跨整月时给 N 个月后/N 个月前
    * 年数：与基准“同月同日”跨年时给 N 年后/N 年前

仅用 Python 标准库；退出码：0 正常，2 参数错误。
"""

import argparse
import calendar
import datetime as dt
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
WEEK_PREFIX = {-2: "上上", -1: "上", 0: "本", 1: "下", 2: "下下"}
DAY_WORDS = {0: "今天", 1: "明天", 2: "后天", 3: "大后天",
             -1: "昨天", -2: "前天", -3: "大前天"}


def parse_date(text):
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"日期格式应为 YYYY-MM-DD，收到 {text!r}")


def monday_of(d):
    return d - dt.timedelta(days=d.weekday())


def month_last_day(d):
    return calendar.monthrange(d.year, d.month)[1]


def expressions(d, base):
    out = []
    delta = (d - base).days
    # 天数
    if delta in DAY_WORDS:
        word = DAY_WORDS[delta]
        if delta != 0:
            word += f"（{abs(delta)} 天{'后' if delta > 0 else '前'}）"
        out.append(word)
    elif delta > 0:
        out.append(f"{delta} 天后")
    else:
        out.append(f"{-delta} 天前")
    # 周数（恰为整周差）
    if delta != 0 and delta % 7 == 0:
        n = abs(delta) // 7
        out.append(f"{n} 周后" if delta > 0 else f"{n} 周前")
    # 星期（±2 周内）
    week_gap = (monday_of(d) - monday_of(base)).days // 7
    if delta != 0 and week_gap in WEEK_PREFIX:
        out.append(f"{WEEK_PREFIX[week_gap]}{WEEK[d.weekday()]}")
    # 月数（与基准同“日”、跨整月）
    month_gap = (d.year * 12 + d.month) - (base.year * 12 + base.month)
    if month_gap != 0 and d.day == base.day:
        out.append(f"{abs(month_gap)} 个月后" if month_gap > 0
                   else f"{abs(month_gap)} 个月前")
    # 年数（与基准同月同日、跨年）
    if d.year != base.year and (d.month, d.day) == (base.month, base.day):
        y = d.year - base.year
        out.append(f"{y} 年后" if y > 0 else f"{-y} 年前")
    # 月初 / 月底
    if month_gap in (-1, 0, 1):
        mark = {-1: "上", 0: "本", 1: "下"}[month_gap]
        if d.day == 1:
            out.append(f"{mark}月初")
        if d.day == month_last_day(d):
            out.append(f"{mark}月底")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="把日期翻译为自然语言相对表达（今天/3 天前/下下周二/月底等）。")
    ap.add_argument("date", type=parse_date, help="目标日期 YYYY-MM-DD")
    ap.add_argument("--base", type=parse_date, default=None,
                    help="基准日期 YYYY-MM-DD（缺省为系统今天）")
    args = ap.parse_args(argv)

    base = args.base if args.base is not None else dt.date.today()
    d = args.date
    print(f"日期：{d.isoformat()}（{WEEK[d.weekday()]}）")
    print(f"基准：{base.isoformat()}（{WEEK[base.weekday()]}）"
          + ("" if args.base is not None else "（默认今天）"))
    print("相对表达：")
    for expr in expressions(d, base):
        print(f"  - {expr}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
