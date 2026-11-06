#!/usr/bin/env python3
"""区域与时区信息（locale-timezone-info）。

输出系统 locale 设置、时区名称与偏移、夏令时状态等区域设置概况，
并尽力探测 zoneinfo（IANA 时区库）可用性。

示例命令：
    python locale-timezone-info.py          # 人读格式
    python locale-timezone-info.py --json   # JSON 输出
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import locale
import os
import sys
import time


def fmt_offset(seconds_east) -> str:
    """把"东经为正"的秒数偏移格式化为 ±HH:MM[:SS]。"""
    total = int(seconds_east)
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if s:
        return "%s%02d:%02d:%02d" % (sign, h, m, s)
    return "%s%02d:%02d" % (sign, h, m)


def collect() -> dict:
    now_local = dt.datetime.now().astimezone()
    now_utc = dt.datetime.now(dt.timezone.utc)
    lt = time.localtime()
    dst_delta = now_local.dst()  # timedelta 或 None

    loc_current = locale.setlocale(locale.LC_ALL)  # 仅查询，不修改
    try:
        loc_env = locale.setlocale(locale.LC_ALL, "")  # 按环境变量应用
    except locale.Error as exc:
        loc_env = "error: %s" % exc
    try:
        pref_enc = locale.getpreferredencoding(False)
    except Exception:
        pref_enc = None
    try:
        loc_cat, loc_enc = locale.getlocale()
    except Exception:
        loc_cat, loc_enc = None, None

    env_vars = {}
    for key in ("LANG", "LC_ALL", "LC_CTYPE", "TZ"):
        if key in os.environ:
            env_vars[key] = os.environ[key]

    info = {
        "locale_current": loc_current,
        "locale_from_env": loc_env,
        "locale_category": loc_cat,
        "locale_encoding": loc_enc,
        "preferred_encoding": pref_enc,
        "env_vars": env_vars,
        "tz_names": list(time.tzname),
        "tz_daylight_support": bool(time.daylight),
        # time.timezone/altzone 为"UTC 偏西"的秒数，这里转成"东偏"便于阅读
        "tz_std_offset_east_seconds": -time.timezone,
        "tz_dst_offset_east_seconds": (-time.altzone) if time.daylight else None,
        "now_local": now_local.isoformat(timespec="seconds"),
        "now_utc": now_utc.isoformat(timespec="seconds"),
        "now_utc_offset": fmt_offset(now_local.utcoffset().total_seconds()),
        "now_dst_active": bool(dst_delta),
        "now_dst_offset": (fmt_offset(dst_delta.total_seconds())
                           if dst_delta else None),
        "tm_isdst": lt.tm_isdst,
    }

    zi = {"available": None, "count": None, "tzname_is_iana": None}
    try:
        from zoneinfo import ZoneInfo, available_timezones

        zi["available"] = True
        zi["count"] = len(available_timezones())
        try:
            ZoneInfo(time.tzname[0])
            zi["tzname_is_iana"] = True
        except Exception:
            zi["tzname_is_iana"] = False
    except Exception as exc:
        zi["available"] = False
        zi["error"] = str(exc)
    info["zoneinfo"] = zi
    return info


def render(info: dict) -> str:
    zi = info["zoneinfo"]
    if zi["available"]:
        if zi["count"]:
            zi_line = "是（共 %s 个时区键）" % zi["count"]
        else:
            zi_line = "模块可用但未找到 tz 数据库（Windows 通常需 pip install tzdata）"
        if not zi["tzname_is_iana"]:
            zi_line += "；系统时区名 %r 不是 IANA 键（Windows 常见，需自行映射）" % (info["tz_names"][0],)
    else:
        zi_line = "否（%s）" % zi.get("error", "缺少 tz 数据")
    lines = [
        "区域与时区信息",
        "-" * 44,
        "当前 locale (LC_ALL) : %s" % info["locale_current"],
        "按环境变量 locale    : %s" % info["locale_from_env"],
        "locale 类别/编码     : %s / %s" % (info["locale_category"],
                                           info["locale_encoding"]),
        "首选编码             : %s" % info["preferred_encoding"],
        "相关环境变量         : %s" % (json.dumps(info["env_vars"], ensure_ascii=False)
                                       if info["env_vars"] else "（未设置 LANG/LC_*/TZ）"),
        "时区名称             : %s" % ", ".join(info["tz_names"]),
        "支持夏令时           : %s" % ("是" if info["tz_daylight_support"] else "否"),
        "标准时区偏移         : %s 秒 (UTC%s)" % (
            info["tz_std_offset_east_seconds"],
            fmt_offset(info["tz_std_offset_east_seconds"])),
        "夏令时偏移           : %s" % (
            ("%s 秒 (UTC%s)" % (info["tz_dst_offset_east_seconds"],
                                fmt_offset(info["tz_dst_offset_east_seconds"])))
            if info["tz_dst_offset_east_seconds"] is not None else "不适用"),
        "当前本地时间         : %s" % info["now_local"],
        "当前 UTC 时间        : %s" % info["now_utc"],
        "当前 UTC 偏移        : %s" % info["now_utc_offset"],
        "当前是否处于夏令时   : %s (tm_isdst=%s)" % (
            "是" if info["now_dst_active"] else "否", info["tm_isdst"]),
        "zoneinfo 可用        : %s" % zi_line,
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="输出系统 locale、时区偏移与夏令时状态等区域设置概况")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    info = collect()
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(render(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
