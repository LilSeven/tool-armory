#!/usr/bin/env python3
"""中国法定节假日查询 —— 内置数据查询中国法定假日与调休补班日，判断某日是否上班。

内置《国务院办公厅关于 2024/2025/2026 年部分节假日安排的通知》中的
放假日期与调休补班日期（2025 年起依据修订后的《全国年节及纪念日放假办法》）。
数据未覆盖的年份仅按周末规则粗判并给出提示。

用法示例:
    python holiday-cn.py 2025-10-01        # 判断该日是否上班
    python holiday-cn.py 2025-10-11        # 调休补班日
    python holiday-cn.py --year 2026       # 列出该年全部假日与补班日
    python holiday-cn.py                   # 判断今天
"""

import argparse
import sys
from datetime import date

WEEKDAY_ZH = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")

# 法定放假日（按国务院历年通知录入; key 为年份, value 为 {节日名: [日期, ...]}）
HOLIDAY_DATA = {
    2024: {
        "元旦": ["2024-01-01"],
        "春节": ["2024-02-10", "2024-02-11", "2024-02-12", "2024-02-13",
                 "2024-02-14", "2024-02-15", "2024-02-16", "2024-02-17"],
        "清明节": ["2024-04-04", "2024-04-05", "2024-04-06"],
        "劳动节": ["2024-05-01", "2024-05-02", "2024-05-03", "2024-05-04",
                  "2024-05-05"],
        "端午节": ["2024-06-10"],
        "中秋节": ["2024-09-15", "2024-09-16", "2024-09-17"],
        "国庆节": ["2024-10-01", "2024-10-02", "2024-10-03", "2024-10-04",
                  "2024-10-05", "2024-10-06", "2024-10-07"],
    },
    2025: {
        "元旦": ["2025-01-01"],
        "春节": ["2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31",
                 "2025-02-01", "2025-02-02", "2025-02-03", "2025-02-04"],
        "清明节": ["2025-04-04", "2025-04-05", "2025-04-06"],
        "劳动节": ["2025-05-01", "2025-05-02", "2025-05-03", "2025-05-04",
                  "2025-05-05"],
        "端午节": ["2025-05-31", "2025-06-01", "2025-06-02"],
        "国庆节·中秋节": ["2025-10-01", "2025-10-02", "2025-10-03", "2025-10-04",
                       "2025-10-05", "2025-10-06", "2025-10-07", "2025-10-08"],
    },
    # 来源: 《国务院办公厅关于2026年部分节假日安排的通知》(2025-11-04 发布)
    2026: {
        "元旦": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "春节": ["2026-02-15", "2026-02-16", "2026-02-17", "2026-02-18",
                 "2026-02-19", "2026-02-20", "2026-02-21", "2026-02-22",
                 "2026-02-23"],
        "清明节": ["2026-04-04", "2026-04-05", "2026-04-06"],
        "劳动节": ["2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04",
                  "2026-05-05"],
        "端午节": ["2026-06-19", "2026-06-20", "2026-06-21"],
        "中秋节": ["2026-09-25", "2026-09-26", "2026-09-27"],
        "国庆节": ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04",
                  "2026-10-05", "2026-10-06", "2026-10-07"],
    },
}

# 调休补班日（周末但需上班的日子）
MAKEUP_DATA = {
    2024: ["2024-02-04", "2024-02-18", "2024-04-07", "2024-04-28", "2024-05-11",
           "2024-09-14", "2024-09-29", "2024-10-12"],
    2025: ["2025-01-26", "2025-02-08", "2025-04-27", "2025-09-28", "2025-10-11"],
    2026: ["2026-01-04", "2026-02-14", "2026-02-28", "2026-05-09", "2026-09-20",
           "2026-10-10"],
}


def _force_utf8_stdio():
    """让输出在 Windows 管道/重定向下也按 UTF-8 编码（Git Bash 友好）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_date(text):
    """解析 YYYY-MM-DD 日期。"""
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError("日期格式应为 YYYY-MM-DD，收到 %r" % text)


def build_indexes():
    """把内置表转换为 {date: 节日名} 与补班日集合。"""
    holiday_by_date = {}
    for by_name in HOLIDAY_DATA.values():
        for name, days in by_name.items():
            for s in days:
                holiday_by_date[date.fromisoformat(s)] = name
    makeup = set()
    for days in MAKEUP_DATA.values():
        makeup.update(date.fromisoformat(s) for s in days)
    return holiday_by_date, makeup


HOLIDAY_BY_DATE, MAKEUP_DATES = build_indexes()
COVERAGE = "%d-%d" % (min(HOLIDAY_DATA), max(HOLIDAY_DATA))


def judge(day):
    """判断某日是否上班，返回 (是否上班, 标签)。"""
    if day in HOLIDAY_BY_DATE:
        return False, "法定假日（%s 假期）" % HOLIDAY_BY_DATE[day]
    if day in MAKEUP_DATES:
        return True, "调休补班日"
    if day.weekday() >= 5:
        return False, "普通周末"
    return True, "普通工作日"


def compress(days):
    """把日期迭代合并为连续区间 [(start, end), ...]。"""
    result = []
    for d in sorted(days):
        if result and (d - result[-1][1]).days == 1:
            result[-1][1] = d
        else:
            result.append([d, d])
    return result


def show_year(year):
    by_name = HOLIDAY_DATA[year]
    total = sum(len(days) for days in by_name.values())
    print("%d 年法定假日（共 %d 天）:" % (year, total))
    for name, days in by_name.items():
        ranges = compress(date.fromisoformat(s) for s in days)
        text = "、".join(
            r[0].isoformat() if r[0] == r[1]
            else "%s ~ %s" % (r[0].isoformat(), r[1].isoformat())
            for r in ranges)
        print("  %s: %s（共 %d 天）" % (name, text, len(days)))
    makeup = sorted(date.fromisoformat(s) for s in MAKEUP_DATA[year])
    print("%d 年调休补班日（共 %d 天，均为上班日）:" % (year, len(makeup)))
    print("  " + "、".join("%s（%s）" % (d.isoformat(), WEEKDAY_ZH[d.weekday()])
                          for d in makeup))


def main(argv=None):
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="查询中国法定假日与调休补班日，判断某日是否上班")
    parser.add_argument("date", nargs="?", type=parse_date, metavar="YYYY-MM-DD",
                        help="要判断的日期（默认今天）")
    parser.add_argument("--year", type=int, metavar="YYYY",
                        help="列出指定年份的假日与补班日")
    args = parser.parse_args(argv)

    if args.year is not None and args.date is not None:
        parser.error("--year 与具体日期不能同时使用")
    if args.year is not None:
        if not 1900 <= args.year <= 2100:
            parser.error("--year 应在 1900-2100 之间")
        if args.year not in HOLIDAY_DATA:
            print("内置数据未覆盖 %d 年（覆盖范围 %s）" % (args.year, COVERAGE))
        else:
            show_year(args.year)
        return 0

    day = args.date if args.date is not None else date.today()
    works, tag = judge(day)
    print("%s（%s）: %s -> %s"
          % (day.isoformat(), WEEKDAY_ZH[day.weekday()], tag,
             "上班" if works else "不上班"))
    if day.year not in HOLIDAY_DATA:
        print("注: 内置数据未覆盖 %d 年（覆盖范围 %s），以上仅按周末规则粗判"
              % (day.year, COVERAGE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
