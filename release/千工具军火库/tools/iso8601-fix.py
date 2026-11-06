#!/usr/bin/env python3
"""ISO 8601 宽松解析与规范化。

宽松解析各种 ISO 8601 写法并统一输出规范格式：
    - 基本格式与扩展格式：20261102 / 2026-11-02 / 2026-11-02T12 / 123045；
    - 缺失部分自动补全：缺时间补 00:00:00，缺秒补 :00；
    - 时区补全：无时区时按 --tz（默认 +00:00）补；Z/z、±HH:MM、
      ±HHMM、±HH 均识别；
    - 周日期 2026-W44-5、序数日期 2026-310 也可解析；
    - 统一输出为扩展格式 YYYY-MM-DDTHH:MM:SS±HH:MM（或 Z），
      可用 --format basic / --utc 额外转换。
无法解析时退出码 2 并说明原因。

仅用 Python 标准库，单文件。

示例命令：
    python -I iso8601-fix.py "2026-11-02 12:34" --tz +08:00
    python -I iso8601-fix.py "20261102T123045Z" --utc
    python -I iso8601-fix.py "2026-W44-5" "2026-310"
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys


def _tz(offset_str: str) -> dt.timezone:
    if offset_str in ("Z", "z"):
        return dt.timezone.utc
    sign = 1 if offset_str[0] == "+" else -1
    digits = offset_str[1:].replace(":", "")
    hh = int(digits[:2])
    mm = int(digits[2:4]) if len(digits) >= 4 else 0
    return dt.timezone(sign * dt.timedelta(hours=hh, minutes=mm))


def normalize(value: str, default_tz: dt.timezone):
    """宽松解析 ISO 8601，返回 (aware datetime, 小数秒字符串)。失败抛 ValueError。"""
    v = value.strip()
    if v == "":
        raise ValueError("空字符串")
    v = v.replace(" ", "T", 1) if "T" not in v and " " in v else v

    # 拆出时区部分
    tz = None
    m_tz = re.search(r"(Z|z|[+-]\d{2}:?\d{2}|[+-]\d{2})$", v)
    if m_tz and not re.fullmatch(r"\d{8}", v):  # 防止 20261102 被吞 +08
        # 尾部形如 +HH / +HHMM / +HH:MM / Z
        cand = m_tz.group(1)
        head = v[:m_tz.start()]
        if re.fullmatch(r"(\d{4}-\d{2}-\d{2}|\d{8})", head):
            # 只有日期，尾部 +08 更可能是日期本身而非时区
            if not re.fullmatch(r"Z|z|[+-]\d{2}:?\d{2}", cand):
                cand = None
        if cand:
            tz = _tz(cand)
            v = head

    # 拆日期与时间
    if "T" in v:
        date_s, time_s = v.split("T", 1)
    else:
        date_s, time_s = v, ""

    # 周日期 YYYY-Www-D（扩展）或 YYYYWwwD（基本）
    m = re.fullmatch(r"(\d{4})-?W(\d{2})-?(\d)?", date_s)
    if m:
        y, w = int(m.group(1)), int(m.group(2))
        d = int(m.group(3) or 1)
        base = dt.date.fromisocalendar(y, w, d)
    else:
        # 序数日期 YYYY-DDD / YYYYDDD
        m = re.fullmatch(r"(\d{4})-?(\d{3})", date_s)
        if m:
            y, doy = int(m.group(1)), int(m.group(2))
            base = dt.date(y, 1, 1) + dt.timedelta(days=doy - 1)
            if base.year != y:
                raise ValueError(f"序数日期 {doy} 超出 {y} 年天数")
            date_s = base.isoformat()
        else:
            m = re.fullmatch(r"(\d{4})-?(\d{2})?-?(\d{2})?", date_s)
            if not m or not m.group(2):
                raise ValueError(f"无法识别的日期部分: {date_s!r}")
            y = int(m.group(1))
            mo = int(m.group(2))
            d = int(m.group(3) or 1)
            base = dt.date(y, mo, d)

    # 时间部分：HH / HHMM / HHMMSS / HH:MM(:SS(.frac)?)?
    sec, frac = 0, ""
    if time_s:
        m = re.fullmatch(r"(\d{2}):?(\d{2})?:?(\d{2})?(\.\d+)?", time_s)
        if not m:
            raise ValueError(f"无法识别的时间部分: {time_s!r}")
        hh = int(m.group(1))
        mi = int(m.group(2) or 0)
        sec = int(m.group(3) or 0)
        frac = m.group(4) or ""
        if hh > 24 or mi > 59 or sec > 60:
            raise ValueError(f"时间数值越界: {time_s!r}")
    else:
        hh, mi = 0, 0

    if tz is None:
        tz = default_tz
    return dt.datetime(base.year, base.month, base.day, hh, mi, sec, tzinfo=tz), frac


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="宽松解析 ISO 8601 并规范化输出")
    ap.add_argument("values", nargs="+", help="ISO 8601 字符串，可给多个")
    ap.add_argument("--tz", default="+00:00",
                    help="缺失时区时补的偏移，默认 +00:00，如 +08:00")
    ap.add_argument("--utc", action="store_true", help="输出前统一换算为 UTC（Z 结尾）")
    ap.add_argument("--format", choices=("extended", "basic"), default="extended",
                    help="输出扩展格式（默认，带分隔符）或基本格式")
    ns = ap.parse_args(argv)

    try:
        default_tz = _tz(ns.tz)
    except (ValueError, IndexError):
        print(f"错误：--tz {ns.tz!r} 不是合法偏移（应为 Z、±HH:MM、±HH）", file=sys.stderr)
        return 2

    failed = False
    for v in ns.values:
        try:
            moment, frac = normalize(v, default_tz)
        except ValueError as exc:
            print(f"[FAIL] {v!r}：{exc}", file=sys.stderr)
            failed = True
            continue
        out = moment
        if ns.utc:
            out = out.astimezone(dt.timezone.utc)
        if ns.format == "basic":
            s = out.strftime("%Y%m%dT%H%M%S")
        else:
            s = out.strftime("%Y-%m-%dT%H:%M:%S")
        if frac:
            s += frac
        if out.tzinfo is dt.timezone.utc:
            s += "Z"
        else:
            off = out.tzinfo.utcoffset(out)
            total = int(off.total_seconds())
            sign = "+" if total >= 0 else "-"
            total = abs(total)
            s += f"{sign}{total // 3600:02d}:{total % 3600 // 60:02d}"
        print(f"[OK] {v!r} -> {s}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
