#!/usr/bin/env python3
"""加班时长统计 —— 从上下班打卡记录计算每日超出标准工时的加班时长并汇总。

读取 CSV 打卡文件(每行一条: 日期,上班HH:MM,下班HH:MM), 计算每日实际工时:
    打卡时长 = 下班 - 上班 (下班时间小于上班时间视为跨零点, 按次日下班计算)
    计工时   = 打卡时长 - 每日午休(--lunch, 默认 60 分钟, 每天最多扣一次)
    加班     = 计工时 - 每日标准工时(--standard, 默认 8 小时), 可为负
同一日期可有多段打卡, 按天累加。空行与 # 开头的注释行被忽略;
无法解析的行打印警告到 stderr 并跳过, 不影响其余记录。

示例:
  python overtime-calc.py records.csv
  python overtime-calc.py records.csv --standard 7.5 --lunch 30
  python overtime-calc.py records.csv --lunch 0          # 不扣午休
"""

import argparse
import re
import sys
import unicodedata
from datetime import date

_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})$")


def dw(s):
    """显示宽度: 全角字符按 2 列计。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def pad_r(s, w):
    return s + " " * max(0, w - dw(s))


def pad_l(s, w):
    return " " * max(0, w - dw(s)) + s


def parse_minutes(text):
    m = _TIME_RE.match(text.strip())
    if not m:
        raise ValueError(f"时间需为 HH:MM, 得到 {text.strip()!r}")
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        raise ValueError(f"时间数值越界: {text.strip()!r}")
    return h * 60 + mi


def parse_line(raw):
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 3:
        raise ValueError("需为 逗号分隔的 日期,上班,下班 三段")
    d = date.fromisoformat(parts[0])
    t_in, t_out = parse_minutes(parts[1]), parse_minutes(parts[2])
    span = t_out - t_in
    if span < 0:
        span += 24 * 60  # 跨零点
    if span == 0:
        raise ValueError("上下班时间相同, 时长为 0")
    return d, span


def load_records(path):
    days, skipped = {}, 0
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                d, span = parse_line(line)
            except ValueError as exc:
                skipped += 1
                print(f"警告: 第 {lineno} 行已跳过: {exc}", file=sys.stderr)
                continue
            days[d] = days.get(d, 0) + span
    return days, skipped


def fmt_hours(minutes):
    return f"{minutes / 60:.2f}h"


def fmt_signed(minutes):
    if minutes > 0:
        return "+" + fmt_hours(minutes)
    if minutes < 0:
        return "-" + fmt_hours(-minutes)
    return "0.00h"


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(
        description="从打卡记录统计每日超出标准工时的加班时长并汇总")
    ap.add_argument("file", help="打卡 CSV 文件, 每行: 日期,上班HH:MM,下班HH:MM")
    ap.add_argument("--standard", type=float, default=8.0,
                    help="每日标准工时(小时), 默认 8")
    ap.add_argument("--lunch", type=float, default=60.0,
                    help="每日午休扣除(分钟), 默认 60, 每天最多扣一次")
    args = ap.parse_args()

    if args.standard <= 0:
        ap.error("--standard 必须大于 0")
    if args.lunch < 0:
        ap.error("--lunch 不能为负")
    try:
        days, skipped = load_records(args.file)
    except OSError as exc:
        print(f"错误: 无法读取 {args.file}: {exc}", file=sys.stderr)
        return 1

    if not days:
        print("错误: 文件中没有有效打卡记录", file=sys.stderr)
        return 1

    std_min = int(round(args.standard * 60))
    lunch_min = int(round(args.lunch))
    rows = []
    tot_gross = tot_net = tot_over = over_days = 0
    for d in sorted(days):
        gross = days[d]
        net = max(0, gross - lunch_min)
        over = net - std_min
        rows.append((d, gross, net, over))
        tot_gross += gross
        tot_net += net
        tot_over += max(0, over)
        over_days += 1 if over > 0 else 0

    headers = ("日期", "打卡", "计工时", "加班")
    body = [(d.isoformat(), fmt_hours(g), fmt_hours(n), fmt_signed(o))
            for d, g, n, o in rows]
    widths = [max([dw(headers[i])] + [dw(r[i]) for r in body]) for i in range(4)]

    def fmt_row(cells):
        parts = [pad_r(cells[0], widths[0])]
        parts += [pad_l(cells[i], widths[i]) for i in (1, 2, 3)]
        return "  ".join(parts)

    print(fmt_row(headers))
    for r in body:
        print(fmt_row(r))
    print("-" * (sum(widths) + 6))
    summary = (f"汇总: 出勤 {len(rows)} 天 | 总打卡 {fmt_hours(tot_gross)}"
               f" | 总计工时 {fmt_hours(tot_net)} | 总加班 {fmt_hours(tot_over)}"
               f" | 加班天数 {over_days} 天")
    if skipped:
        summary += f" | 跳过无效行 {skipped} 行"
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
