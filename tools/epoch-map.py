#!/usr/bin/env python3
"""多历元时间映射 (epoch-map)

在不同纪元基准之间换算毫秒值：Unix、NTP、Windows FILETIME、Java、COM(COALEDATETIME)、
WebKit/Chrome、macOS 绝对时间。支持 单值转换 与 互转（--to 多目标）。

各纪元与 Unix 的固定偏移（秒）:
  Unix      : 1970-01-01, offset 0
  Java      : 同 Unix，但毫秒为单位（此处即毫秒值，offset 0）
  NTP       : 1900-01-01, offset -2208988800 s
  FILETIME  : 1601-01-01, offset -11644473600 s，单位 100ns（此处折算为 ms）
  COM       : 1899-12-30, offset -2209161600 s
  WebKit    : 1601-01-01 同 FILETIME 但单位为 ms
  macOS     : 2001-01-01, offset +978307200 s

用法:
  python epoch-map.py 1700000000123                    # 自动识别量级，按 Unix ms 换算各历元
  python epoch-map.py 1700000000123 --from ntp --to unix,java
  python epoch-map.py 133700000000000000 --from filetime --to all   # filetime 输入兼容毫秒与 100ns 原生量级（>=1e17 自动 ÷10000 折算并在输出中注明）
  python epoch-map.py --now                            # 当前时刻各历元的毫秒值
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

# 各历元相对 Unix 秒的偏移
EPOCHS = {
    "unix":     0,
    "java":     0,             # 与 Unix 同起点，毫秒
    "ntp":      -2208988800,   # 1900-01-01
    "filetime": -11644473600,  # 1601-01-01，输入输出按 100ns 折算 ms
    "com":      -2209161600,   # 1899-12-30
    "webkit":   -11644473600,  # 同 FILETIME 起点，单位 ms
    "macos":    978307200,     # 2001-01-01 (Core Data)
}

# 各历元"毫秒值"的语义: filetime 的原生单位是 100ns，这里用 ms 表示
NATIVE_UNIT = {
    "filetime": "100ns 单位（输入输出按毫秒折算）",
    "unix": "毫秒", "java": "毫秒", "ntp": "毫秒",
    "com": "毫秒", "webkit": "毫秒", "macos": "毫秒",
}


def to_unix_ms(value, src):
    """把 src 历元的值折算为 Unix ms。

    返回 (unix_ms, note)。filetime 输入兼容两种量级：
    >= 1e17 视为 100ns 原生值（1 ms = 10^4 个 100ns，自动 ÷10000），否则视为毫秒。
    """
    off = EPOCHS[src]
    note = None
    if src == "filetime" and abs(value) >= 10 ** 17:
        value = value // 10000
        note = "输入为 100ns 原生量级，已 ÷10000 折算为 ms"
    # 历元偏移为负（早于 Unix）的历元，其毫秒值更大: unix_ms = value + off*1000
    return value + off * 1000, note


def from_unix_ms(unix_ms, dst):
    off = EPOCHS[dst]
    return unix_ms - off * 1000


def auto_detect_ms(v):
    """按量级猜测毫秒值对应的历元：返回 (name, unix_ms_guess)。"""
    a = abs(v)
    # FILETIME 毫秒口径 ~ 11.7e12 到今; 若输入像 100ns 原生值(>=1e17) 则先当 filetime 原生
    if a >= 10 ** 17:
        # 视为 FILETIME 100ns 原生值（1 ms = 10^4 个 100ns）
        unix_ms = (v // 10000) + EPOCHS["filetime"] * 1000
        return "filetime(100ns)", unix_ms
    if a >= 10 ** 14:
        # 视为 WebKit/FILETIME 毫秒口径
        return "webkit(ms)", v + EPOCHS["webkit"] * 1000
    # 其余默认 Unix ms
    return "unix", v


def fmt_dt(unix_ms):
    try:
        dt = _EPOCH + timedelta(milliseconds=unix_ms)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " UTC"
    except (OverflowError, ValueError):
        return "<超出可表示范围>"


def main():
    ap = argparse.ArgumentParser(description="多纪元基准毫秒值互转")
    ap.add_argument("value", nargs="?", type=int, help="毫秒值（filetime 也可直接给 100ns 原生大数）")
    ap.add_argument("--from", dest="src", choices=sorted(EPOCHS), help="输入所属纪元（缺省自动识别）")
    ap.add_argument("--to", dest="dst", default="all",
                    help="目标纪元，逗号分隔（如 unix,java）或 all")
    ap.add_argument("--now", action="store_true", help="显示当前时刻各历元毫秒值")
    args = ap.parse_args()

    if args.now:
        unix_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        print("当前时刻各历元毫秒值：")
        for name in EPOCHS:
            print("  %-9s %20d   (%s)" % (name, from_unix_ms(unix_ms, name), fmt_dt(unix_ms)))
        return 0

    if args.value is None:
        ap.error("需要提供 value 或使用 --now")

    v = args.value
    note = None
    if args.src:
        unix_ms, note = to_unix_ms(v, args.src)
        src_label = args.src + ("(100ns)" if note else "(ms)")
    else:
        src_label, unix_ms = auto_detect_ms(v)

    print("输入      : %d （按 %s 解读）" % (v, src_label))
    if note:
        print("折算      : %s" % note)
    print("对应 UTC  : %s" % fmt_dt(unix_ms))
    print("-" * 62)
    targets = list(EPOCHS) if args.dst == "all" else [s.strip() for s in args.dst.split(",")]
    for t in targets:
        if t not in EPOCHS:
            print("错误: 未知纪元 %s（可选: %s）" % (t, ", ".join(EPOCHS)), file=sys.stderr)
            return 1
        out = from_unix_ms(unix_ms, t)
        if t == "filetime":
            print("  %-9s %20d   (原生 100ns: %d)" % (t, out, out * 10000))
        else:
            print("  %-9s %20d" % (t, out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
