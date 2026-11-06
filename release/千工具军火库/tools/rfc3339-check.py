#!/usr/bin/env python3
"""RFC 3339 日期时间字符串严格校验器。

按 RFC 3339（ABNF: date-time / full-date / full-time）严格校验输入，
报告第一个不合规的具体位置与原因。规则要点：
    - date-fullyear 4 位数字；date-mday 需结合闰年校验；
    - T（或经 --lower-t 允许小写 t、空格）分隔日期与时间；
    - time-hour 00-23、time-minute 00-59、time-second 00-59（不含 60，
      RFC 3339 允许闰秒 60，用 --leap-second 放行）；
    - 偏移必须为 Z / z（--lower-z 控制小写）或 ±HH:MM，-00:00 视为
      未知本地偏移（合法但提示）；
    - 不允许多余字符、前导/尾随空白（--strict 默认开）。
可校验 date-time（默认）、--date-only、--time-only。

仅用 Python 标准库，单文件。

示例命令：
    python -I rfc3339-check.py "2026-11-02T12:34:56Z"
    python -I rfc3339-check.py "2026-02-29T00:00:00+08:00"
    python -I rfc3339-check.py "2026-13-01T00:00:00Z" --verbose
"""

from __future__ import annotations

import argparse
import calendar
import re
import sys


def check(value: str, *, allow_lower_t: bool = True, allow_space_t: bool = False,
          allow_lower_z: bool = True, allow_leap_second: bool = False):
    """校验 RFC 3339 date-time。返回 (ok, 错误信息或 None, 附注列表)。"""
    notes = []
    if value == "":
        return False, "位置 0：空字符串", notes
    if value != value.strip():
        return False, "位置 0：存在前导/尾随空白，RFC 3339 不允许", notes

    m = re.fullmatch(
        r"(\d{4})-(\d{2})-(\d{2})"
        r"([Tt" + (r" " if allow_space_t else r"") + r"])"
        r"(\d{2}):(\d{2}):(\d{2})(\.\d+)?"
        r"([Zz]|[+-]\d{2}:\d{2})",
        value)
    if not m:
        # 定位第一个不合规字符
        for i, ch in enumerate(value):
            if not (ch.isdigit() or ch in "-Tt:.+Zz "):
                return False, f"位置 {i}：出现不允许的字符 {ch!r}", notes
        return False, "整体结构不符合 RFC 3339（应为 YYYY-MM-DDTHH:MM:SS[.frac]Z|±HH:MM）", notes

    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    sep = m.group(4)
    hh, mm, ss = int(m.group(5)), int(m.group(6)), int(m.group(7))
    frac = m.group(8)
    off = m.group(9)

    if sep == "T" and value.find("T") == -1:
        pass  # 不可能走到
    if sep != "T":
        if sep == "t" and allow_lower_t:
            notes.append("位置 10：使用了小写 't'，RFC 3339 NOTE 允许但建议大写")
        elif sep == " ":
            notes.append("位置 10：使用了空格分隔（非 RFC 3339 date-time 标准写法）")

    if not (1 <= month <= 12):
        return False, f"位置 5：月份 {month:02d} 不在 01-12 范围", notes
    dim = calendar.monthrange(year, month)[1]
    if not (1 <= day <= dim):
        extra = "（闰年才有 2 月 29 日）" if (month, day) == (2, 29) else ""
        return False, f"位置 8：{year}-{month:02d} 月没有 {day} 日{extra}", notes
    if hh > 23:
        return False, f"位置 11：小时 {hh:02d} 超出 00-23", notes
    if mm > 59:
        return False, f"位置 14：分钟 {mm:02d} 超出 00-59", notes
    if ss > 59:
        if ss == 60 and allow_leap_second:
            notes.append("位置 17：秒值为 60（闰秒），RFC 3339 允许但极少见")
        else:
            hint = "；如需接受闰秒可用 --leap-second" if ss == 60 else ""
            return False, f"位置 17：秒 {ss:02d} 不在 00-59 范围{hint}", notes

    if frac:
        notes.append(f"位置 19：含小数秒 {frac}（合法，time-secfrac）")
    if off == "-00:00":
        notes.append("位置 19：-00:00 表示未知本地偏移，合法但含义与 +00:00 不同")
    elif off in ("Z", "z"):
        if off == "z":
            notes.append("位置 19：小写 'z' 可读性差，建议大写 'Z'")
    else:
        oh, om = int(off[1:3]), int(off[4:6])
        if oh > 23 or om > 59:
            return False, f"位置 19：时区偏移 {off} 数值超界（HH<=23, MM<=59）", notes

    return True, None, notes


def check_date(value: str):
    notes = []
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value)
    if not m:
        return False, "不符合 full-date（应为 YYYY-MM-DD）", notes
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= month <= 12):
        return False, f"位置 5：月份 {month:02d} 不在 01-12 范围", notes
    dim = calendar.monthrange(year, month)[1]
    if not (1 <= day <= dim):
        return False, f"位置 8：{year}-{month:02d} 月没有 {day} 日", notes
    return True, None, notes


def check_time(value: str, *, allow_leap_second: bool = False):
    notes = []
    m = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})(\.\d+)?([Zz]|[+-]\d{2}:\d{2})", value)
    if not m:
        return False, "不符合 full-time（应为 HH:MM:SS[.frac]Z|±HH:MM）", notes
    hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if hh > 23:
        return False, f"位置 0：小时 {hh:02d} 超出 00-23", notes
    if mm > 59:
        return False, f"位置 3：分钟 {mm:02d} 超出 00-59", notes
    if ss > 59 and not (ss == 60 and allow_leap_second):
        return False, f"位置 6：秒 {ss:02d} 不在 00-59 范围", notes
    if m.group(4):
        notes.append(f"含小数秒 {m.group(4)}（合法）")
    return True, None, notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="严格校验 RFC 3339 日期时间字符串")
    ap.add_argument("values", nargs="+", help="待校验字符串，可给多个")
    ap.add_argument("--date-only", action="store_true", help="按 full-date 校验")
    ap.add_argument("--time-only", action="store_true", help="按 full-time 校验")
    ap.add_argument("--no-lower-t", action="store_true", help="禁止小写 t 分隔符")
    ap.add_argument("--allow-space-t", action="store_true", help="允许空格分隔日期与时间")
    ap.add_argument("--leap-second", action="store_true", help="允许秒值为 60（闰秒）")
    ap.add_argument("--verbose", action="store_true", help="输出附注信息")
    ns = ap.parse_args(argv)

    all_ok = True
    for v in ns.values:
        if ns.date_only:
            ok, err, notes = check_date(v)
        elif ns.time_only:
            ok, err, notes = check_time(v, allow_leap_second=ns.leap_second)
        else:
            ok, err, notes = check(
                v, allow_lower_t=not ns.no_lower_t, allow_space_t=ns.allow_space_t,
                allow_leap_second=ns.leap_second)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {v!r}")
        if err:
            print(f"    原因：{err}")
        if ns.verbose:
            for n in notes:
                print(f"    附注：{n}")
        all_ok = all_ok and ok
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
