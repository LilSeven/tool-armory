#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""星期几查询 —— 输出指定日期的星期几，一次给出中/英/日/德/法/西/俄/韩多语言星期名称。

用法:
    python weekday-of.py 2026-11-02              # 输出该日期在全部支持语言下的星期名称
    python weekday-of.py 2026-11-02 --lang ja    # 只输出日语
    python weekday-of.py 2026-11-02 --lang en --iso   # 英语 + ISO 8601 周号
    python weekday-of.py today                   # 亦接受 today / tomorrow / yesterday

示例输出:
    $ python weekday-of.py 2026-11-02
    2026-11-02 的星期几:
      zh  星期一
      en  Monday
      ja  月曜日
      ...

退出码: 0 成功; 2 日期格式错误或参数错误。
仅用 Python 标准库。
"""

import argparse
import sys
from datetime import date, timedelta

# date.weekday(): 0=周一 ... 6=周日
WEEKDAYS = {
    "zh": ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "ja": ["月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"],
    "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
    "fr": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
    "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
    "ru": ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"],
    "ko": ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"],
}
ORDER = ["zh", "en", "ja", "de", "fr", "es", "ru", "ko"]


def parse_date(text):
    """解析 YYYY-MM-DD 或 today/tomorrow/yesterday，失败抛 ValueError。"""
    t = text.strip().lower()
    today = date.today()
    if t == "today":
        return today
    if t == "tomorrow":
        return today + timedelta(days=1)
    if t == "yesterday":
        return today - timedelta(days=1)
    return date.fromisoformat(t)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="输出指定日期的星期几（多语言：中/英/日/德/法/西/俄/韩）")
    p.add_argument("date", help="日期 YYYY-MM-DD，或 today/tomorrow/yesterday")
    p.add_argument("--lang", choices=ORDER, help="只输出指定语言的星期名称")
    p.add_argument("--iso", action="store_true", help="附带显示 ISO 8601 周号")
    args = p.parse_args(argv)

    try:
        d = parse_date(args.date)
    except ValueError:
        print(f"错误: 无法解析日期 {args.date!r}，请使用 YYYY-MM-DD", file=sys.stderr)
        return 2

    idx = d.weekday()
    if args.lang:
        print(WEEKDAYS[args.lang][idx])
        return 0

    print(f"{d.isoformat()} 的星期几:")
    for lang in ORDER:
        print(f"  {lang}  {WEEKDAYS[lang][idx]}")
    if args.iso:
        y, w, _ = d.isocalendar()
        print(f"  ISO 周号: {y}-W{w:02d}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
