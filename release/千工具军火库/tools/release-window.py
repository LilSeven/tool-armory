#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发版窗口检查（release-window）——判断候选发布日期是否落在周五、节假日前等高风险窗口并给出建议。

用途：
    对一个或多个候选发布日期做上线风险评估：
      · 周五发布（随后进入周末，故障响应人手不足）→ 高风险；
      · 发布后紧接连续休息日：≥3 天（长假期前）→ 高风险，2 天（周末/小
        长假前）→ 需谨慎，1 天 → 仅提示；
      · 月末/季末最后工作日（变更冻结期）→ 需谨慎。
    逐条给出理由，并为有风险的日期推荐之后 30 天内第一个安全工作日。

示例：
    python release-window.py --date 2026-11-06
    python release-window.py --date 2026-11-25,2026-12-31 --holidays 2026-11-26,2026-11-27
    python release-window.py --date 2027-01-01 --holidays 2027-01-01..2027-01-03

退出码：0 成功（检查本身完成）；2 参数错误。
"""

import argparse
import datetime as dt
import sys

WEEK_CN = "一二三四五六日"
LEVEL_TEXT = {0: "[OK] 可以发布", 1: "[CAUTION] 需谨慎", 2: "[HIGH] 高风险"}


def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _date(s):
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError("无效日期 %r，应为 YYYY-MM-DD" % s)


def _date_list(s):
    out = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if ".." in part:
            a, _, b = part.partition("..")
            start, end = _date(a.strip()), _date(b.strip())
            if end < start:
                raise argparse.ArgumentTypeError(
                    "无效日期区间 %r：起始日期晚于结束日期" % part)
            if (end - start).days > 36600:
                raise argparse.ArgumentTypeError(
                    "日期区间 %r 跨度过大（最多支持 100 年）" % part)
            cur = start
            while cur <= end:
                out.append(cur)
                cur += dt.timedelta(days=1)
        else:
            out.append(_date(part))
    if not out:
        raise argparse.ArgumentTypeError("日期列表不能为空")
    return out


def is_off(d, holidays, makeups):
    return d in holidays or (d.weekday() >= 5 and d not in makeups)


def assess(d, holidays, makeups):
    """返回 (风险等级 0/1/2, [(等级, 说明), ...])。"""

    def work(x):
        return not is_off(x, holidays, makeups)

    reasons = []
    gap = 0
    nd = d + dt.timedelta(days=1)
    while not work(nd):
        gap += 1
        nd += dt.timedelta(days=1)
    if d.weekday() == 4:
        if gap == 0:
            reasons.append((1, "周五发布（次日为调休工作日，风险略降）"))
        else:
            reasons.append((2, "周五发布：随后进入周末，线上故障响应人手不足"))
    if gap >= 3:
        reasons.append((2, "发布后进入 %d 天连续休息期（长假期前发布，期间无人值守）" % gap))
    elif gap == 2:
        reasons.append((1, "发布后连续 2 天无工作日（周末/小长假前）"))
    elif gap == 1:
        reasons.append((0, "发布次日为休息日（留意休息期间的值班安排）"))
    if nd.month != d.month:
        tag = "季末" if d.month in (3, 6, 9, 12) else "月末"
        reasons.append((1, "%s最后工作日发布（变更冻结期，观察与回滚窗口受限）" % tag))
    level = max((lvl for lvl, _ in reasons), default=0)
    return level, reasons


def next_safe(d, holidays, makeups, horizon=30):
    for i in range(1, horizon + 1):
        c = d + dt.timedelta(days=i)
        if is_off(c, holidays, makeups):
            continue
        level, _ = assess(c, holidays, makeups)
        if level == 0:
            return c
    return None


def main(argv=None):
    _utf8_stdio()
    p = argparse.ArgumentParser(
        description="判断候选发布日期是否落在周五、节假日前等高风险窗口并给出建议")
    p.add_argument("--date", required=True,
                   help="候选发布日期，多个用逗号分隔，如 2026-11-06,2026-11-25")
    p.add_argument("--holidays", type=_date_list, default=[],
                   help="放假日表，逗号分隔，支持 a..b 区间（含两端）")
    p.add_argument("--workdays", type=_date_list, default=[],
                   help="调休补班日（周末上班），逗号分隔")
    args = p.parse_args(argv)

    dates = sorted(set(_date_list(args.date)))
    holidays = set(args.holidays)
    makeups = set(args.workdays)

    print("发布窗口检查 · %d 个候选日期 · 放假 %d 天 / 补班 %d 天" %
          (len(dates), len(holidays), len(makeups)))
    for d in dates:
        level, reasons = assess(d, holidays, makeups)
        print("-" * 64)
        print("候选日期：%s（周%s） → %s" %
              (d.isoformat(), WEEK_CN[d.weekday()], LEVEL_TEXT[level]))
        if reasons:
            for lvl, txt in sorted(reasons, key=lambda r: -r[0]):
                print("  - %s" % txt)
        else:
            print("  - 常规工作日，未识别到已知风险模式")
        if level > 0:
            alt = next_safe(d, holidays, makeups)
            if alt:
                print("  建议：改期至 %s（周%s）或更早的安全工作日" %
                      (alt.isoformat(), WEEK_CN[alt.weekday()]))
            else:
                print("  建议：30 天内未找到完全无风险的日期，请人工评估")
    print("-" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
