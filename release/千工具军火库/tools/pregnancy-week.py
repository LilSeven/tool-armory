#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""孕周预产期计算：按末次月经日期计算当前孕周孕天、预产期与孕程进度。

用途：
    按末次月经首日（LMP）与基准日期（默认今天）计算：
      - 当前孕周孕天（孕X周+Y天）、孕月（每4周为一孕月）与孕早/中/晚期；
      - 预产期（LMP + 280 天，即孕 40 周）及其星期、倒计时或超期天数；
      - 孕程进度百分比、足月日与主要产检节点窗口日期。

用法：
    python pregnancy-week.py --lmp <YYYY-MM-DD> [--at YYYY-MM-DD]

示例命令：
    python pregnancy-week.py --lmp 2026-05-01
    python pregnancy-week.py --lmp 2026-05-01 --at 2026-11-02

说明：
    - 预产期按内格勒法则（Naegele's rule）：LMP + 280 天；
    - 分期：孕早期 <14 周（≤13周+6天），孕中期 14-27周+6，孕晚期 ≥28 周；
    - 计算结果仅供参考，产检安排请遵医嘱；
    - 仅使用 Python 标准库；退出码：0 成功，2 参数/日期错误。
"""

import argparse
import sys
from datetime import date, timedelta

WEEK_CN = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
TOTAL_DAYS = 280  # 孕 40 周


def week_cn(d):
    return WEEK_CN[d.weekday()]


def run(lmp, ref, at_default):
    if ref < lmp:
        raise ValueError("基准日期早于末次月经日期")
    gd = (ref - lmp).days
    edd = lmp + timedelta(days=TOTAL_DAYS)
    weeks, rem = divmod(gd, 7)
    if gd < 14 * 7:
        stage = "孕早期"
    elif gd < 28 * 7:
        stage = "孕中期"
    else:
        stage = "孕晚期"
    preg_month = min(gd // 28 + 1, 10)

    print(f"末次月经：{lmp.isoformat()}（{week_cn(lmp)}）")
    print(f"基准日期：{ref.isoformat()}（{week_cn(ref)}）" + ("（默认今天）" if at_default else ""))
    print(f"当前孕周：孕{weeks}周+{rem}天（第 {preg_month} 个孕月，{stage}）")
    if gd > TOTAL_DAYS:
        print(f"孕程进度：已超过预产期 {gd - TOTAL_DAYS} 天（{gd} / 280 天）")
    else:
        print(f"孕程进度：{gd / TOTAL_DAYS * 100:.1f}%（{gd} / 280 天）")
    print(f"预产期：{edd.isoformat()}（{week_cn(edd)}，孕40周）"
          + (f"，还有 {TOTAL_DAYS - gd} 天" if gd <= TOTAL_DAYS else ""))
    full_term = lmp + timedelta(days=37 * 7)
    if gd >= 37 * 7:
        print(f"足月日：{full_term.isoformat()}（孕37周）——已足月")
    else:
        print(f"足月日：{full_term.isoformat()}（孕37周），还有 {37 * 7 - gd} 天")
    if gd > 294:
        print("提示：已超过 42 周，请及时就医核实孕周与日期。")

    nodes = [
        ("NT检查窗口（孕11周0天-13周6天）", 77, 97),
        ("中唐筛查窗口（孕15-20周）", 105, 140),
        ("大排畸/系统超声（孕20-24周）", 140, 168),
        ("糖耐量OGTT窗口（孕24-28周）", 168, 196),
    ]
    print("产检节点（按 LMP 推算，具体安排请遵医嘱）：")
    for name, s, e in nodes:
        if gd > e:
            mark = "已过"
        elif gd >= s:
            mark = "进行中"
        else:
            mark = "未到"
        print(f"  [{mark}] {name}：{lmp + timedelta(days=s)} ~ {lmp + timedelta(days=e)}")


def parse_date(s):
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        raise argparse.ArgumentTypeError(f"日期格式应为 YYYY-MM-DD，收到：{s!r}")


def _utf8_stdio():
    """在非 UTF-8 控制台/管道下尽量以 UTF-8 输出。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (stream.encoding or "").lower().replace("-", "")
            if enc and enc != "utf8" and hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv=None):
    _utf8_stdio()
    p = argparse.ArgumentParser(
        prog="pregnancy-week.py",
        description="孕周预产期计算：按末次月经日期计算孕周孕天、预产期与孕程进度。")
    p.add_argument("--lmp", type=parse_date, metavar="YYYY-MM-DD", required=True,
                   help="末次月经首日")
    p.add_argument("--at", type=parse_date, metavar="YYYY-MM-DD", default=None,
                   help="基准日期，默认今天")
    args = p.parse_args(argv)
    ref = args.at or date.today()
    try:
        run(args.lmp, ref, args.at is None)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
