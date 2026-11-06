#!/usr/bin/env python3
"""ISO 周号查询 —— 查询日期所属的 ISO 年/周/星期, 或由年+周号反查该周日期区间。

用法:
  python iso-week.py 2026-01-01        # 查日期: ISO 年, 周号, 星期与本周区间
  python iso-week.py 2026-W01          # 周记法(2026W01 / 2026-W1 亦可)
  python iso-week.py 2026 1            # 反查: ISO 2026 第 1 周的周一~周日
  python iso-week.py 2026 27 --day 3   # 反查并给出该周第 3 天(周三)的日期

遵循 ISO 8601: 一周从周一开始, 第 1 周是包含当年第一个星期四的那一周;
年+周 反查时若周号超出该年范围(如 2025 年第 53 周)则报错, 退出码 1。
"""

import argparse
import re
import sys
from datetime import date, timedelta

CN_DAY = "一二三四五六日"
_WEEK_RE = re.compile(r"^(\d{1,4})-?[wW](\d{1,2})$")


def fail(msg):
    print(f"错误: {msg}", file=sys.stderr)
    return 1


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="ISO 周号与日期区间互查")
    ap.add_argument("items", nargs="+",
                    help="日期(YYYY-MM-DD 或 YYYY-Www), 或 '年 周' 两个参数")
    ap.add_argument("--day", type=int, choices=range(1, 8), metavar="N",
                    help="反查模式下给出该周第 N 天(1=周一 ... 7=周日)")
    return ap.parse_args(argv)


def week_range(year, week):
    monday = date.fromisocalendar(year, week, 1)
    return monday, monday + timedelta(days=6)


def query_week(year, week, day):
    try:
        monday, sunday = week_range(year, week)
    except ValueError:
        return fail(f"ISO {year} 年不存在第 {week} 周"
                    f"(该年只有 52 或 53 周, 周号需在 1-52/53 之间)")
    print(f"ISO {year} 第 {week:02d} 周: "
          f"{monday.isoformat()}(周一) ~ {sunday.isoformat()}(周日)")
    if day is not None:
        d = date.fromisocalendar(year, week, day)
        print(f"  第 {day} 天(星期{CN_DAY[d.weekday()]}): {d.isoformat()}")
    return 0


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = parse_args()

    if len(args.items) == 1:
        token = args.items[0].strip()
        m = _WEEK_RE.match(token)
        if m:
            return query_week(int(m.group(1)), int(m.group(2)), args.day)
        try:
            d = date.fromisoformat(token)
        except ValueError:
            return fail(f"无法解析 {token!r}; 支持 YYYY-MM-DD / YYYY-Www, "
                        f"或 '年 周' 两个参数")
        if args.day is not None:
            print("提示: --day 仅在 年+周 反查模式下生效, 已忽略", file=sys.stderr)
        iso = d.isocalendar()
        monday = d - timedelta(days=d.weekday())
        sunday = monday + timedelta(days=6)
        print(f"{d.isoformat()} → ISO {iso[0]} 年第 {iso[1]:02d} 周, "
              f"星期{CN_DAY[d.weekday()]}"
              f" (记法 {iso[0]}-W{iso[1]:02d}-{d.isoweekday()})")
        print(f"本周区间: {monday.isoformat()}(周一) ~ {sunday.isoformat()}(周日)")
        return 0

    if len(args.items) == 2:
        try:
            year, week = int(args.items[0]), int(args.items[1])
        except ValueError:
            return fail("年 与 周 需为整数, 如: iso-week.py 2026 27")
        return query_week(year, week, args.day)

    return fail("参数过多: 只接受 1 个日期, 或 '年 周' 两个参数")


if __name__ == "__main__":
    sys.exit(main())
