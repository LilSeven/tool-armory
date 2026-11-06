#!/usr/bin/env python3
"""Excel 序列号换算 —— Excel 1900 日期序列号与公历日期互转，正确处理 1900 闰年 bug。

用法:
    python excel-serial.py --serial 45800            # 序列号 -> 日期
    python excel-serial.py --serial 45800.75         # 含小数 (时间部分)
    python excel-serial.py --date 2026-05-12         # 日期 -> 序列号
    python excel-serial.py --date 2026-05-12 --time 18:00
    python excel-serial.py --serial 60               # 1900 闰年 bug 演示

说明:
    Excel 1900 日期系统: 序列号 1 = 1900-01-01。但 Excel 误把 1900 当闰年，
    序列号 60 对应不存在的 1900-02-29。因此:
      - 序列号 1..59  -> 1900-01-01 .. 1900-02-28
      - 序列号 60     -> 不存在 (Excel 中的假日期 1900-02-29)
      - 序列号 >= 61  -> 真实日期 = 1899-12-30 + 序列号 天
    反向换算: 1900-03-01 及以后 = 日期 - 1899-12-30；1900-01-01..1900-02-28 = 日期 - 1899-12-31。
    Excel 不支持 1900-01-01 之前的日期（序列号 0 是伪值 "1900-01-00"）。
仅使用 Python 标准库。
"""

import argparse
import datetime as dt
import sys

# 基准锚点
_ANCHOR_AFTER = dt.date(1899, 12, 30)   # 序列号 >= 61 的真实日期锚点
_ANCHOR_BEFORE = dt.date(1899, 12, 31)  # 序列号 1..59 的锚点
_MIN_SERIAL, _MAX_SERIAL = 1, 9999_12_31  # Excel 支持到 9999-12-31


def serial_to_date(serial):
    """Excel 序列号 -> (date, 时间部分, 备注)。返回备注解释 1900 bug。"""
    if serial < 0:
        raise ValueError(f"序列号必须 >= 0，收到 {serial}")
    frac = serial - int(serial)
    whole = int(serial)
    note = None

    if whole == 0:
        if frac:
            return None, frac, "序列号 0 是 Excel 的伪日期 '1900-01-00'，仅时间部分有意义"
        return None, 0.0, "序列号 0 是 Excel 的伪日期 '1900-01-00'，不对应真实日期"
    if whole == 60:
        # 1900 闰年 bug: Excel 显示为不存在的 1900-02-29
        note = ("1900 闰年 bug: 序列号 60 在 Excel 中显示为 1900-02-29，"
                "但该日期并不存在（1900 年不是闰年）")
        return None, frac, note
    if whole < 60:
        d = _ANCHOR_BEFORE + dt.timedelta(days=whole)
    else:
        d = _ANCHOR_AFTER + dt.timedelta(days=whole)
    if d > dt.date(9999, 12, 31):
        raise ValueError(f"序列号 {serial} 超出可表示范围 (最大对应 9999-12-31)")
    return d, frac, note


def date_to_serial(d, frac=0.0):
    """公历日期 -> Excel 序列号；1900-01-01 之前无法表示。"""
    if d < dt.date(1900, 1, 1):
        raise ValueError(f"Excel 1900 日期系统不支持 {d} (早于 1900-01-01)")
    if d <= dt.date(1900, 2, 28):
        serial = (d - _ANCHOR_BEFORE).days
    else:
        serial = (d - _ANCHOR_AFTER).days
    return serial + frac


def fmt_time(frac):
    """序列号小数部分 -> HH:MM:SS 文本。"""
    if not frac:
        return ""
    seconds = round(frac * 86400)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f" {h:02d}:{m:02d}:{s:02d}"


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Excel 1900 序列号与公历日期互转（处理 1900 闰年 bug）")
    p.add_argument("--serial", type=float, metavar="N",
                   help="Excel 序列号，如 45800 或 45800.75")
    p.add_argument("--date", metavar="YYYY-MM-DD", help="公历日期，如 2026-05-12")
    p.add_argument("--time", metavar="HH:MM[:SS]", help="可选时间部分，与 --date 同用")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.serial is None and not args.date:
        raise SystemExit("错误: 请用 --serial N 或 --date YYYY-MM-DD 指定要换算的内容")
    if args.serial is not None and args.date:
        raise SystemExit("错误: --serial 与 --date 只能二选一")

    if args.serial is not None:
        d, frac, note = serial_to_date(args.serial)
        if d is None:
            print(f"序列号 {args.serial:g}: {note or '无对应日期'}")
            if frac:
                print(f"  时间部分 = {fmt_time(frac).strip()}")
            return 0
        print(f"序列号 {args.serial:g} -> {d.isoformat()}{fmt_time(frac)}"
              f"  ({d:%A}, 星期{'一二三四五六日'[d.weekday()]})")
        if note:
            print(f"  备注: {note}")
        # 往返验证
        back = date_to_serial(d, frac) if d >= dt.date(1900, 1, 1) else None
        if back is not None and abs(back - args.serial) > 1e-9:
            print(f"  警告: 往返校验不一致 ({back})")
        return 0

    try:
        d = dt.date.fromisoformat(args.date)
    except ValueError:
        raise SystemExit(f"错误: 日期格式应为 YYYY-MM-DD，收到 {args.date!r}")
    frac = 0.0
    if args.time:
        try:
            parts = [int(x) for x in args.time.split(":")]
            h, m, s = (parts + [0, 0])[:3]
            frac = (h * 3600 + m * 60 + s) / 86400
        except (ValueError, IndexError):
            raise SystemExit(f"错误: 时间格式应为 HH:MM[:SS]，收到 {args.time!r}")
    try:
        serial = date_to_serial(d, frac)
    except ValueError as e:
        raise SystemExit(f"错误: {e}")
    print(f"日期 {d.isoformat()}{fmt_time(frac)} -> Excel 序列号 {serial:g}"
          f"  (整数部分 {int(serial)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
