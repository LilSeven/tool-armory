#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""uuid7-gen.py —— RFC 9562 UUIDv7 生成器（单文件，纯 Python 标准库）。

UUIDv7 结构：48 位 Unix 毫秒时间戳 | 4 位版本号(7) | 12 位 rand_a | 2 位变体(10) | 62 位 rand_b。
随机位取自 secrets；同一毫秒内以 rand_a 作为 12 位单调计数器，保证本进程内
生成的 UUID 字典序 = 时间序；含时钟回拨保护与计数器溢出处理（溢出时时间戳前移 1ms）。

用法：
    python -I uuid7-gen.py [-n 数量] [--upper] [--selftest]

示例命令：
    python -I "K:/WorkAreaZcode/tool-armory/tools/uuid7-gen.py" -n 5
    python -I "K:/WorkAreaZcode/tool-armory/tools/uuid7-gen.py" -n 3 --upper

示例输出（每次运行不同）：
    018f3a2b-7c1d-7e4f-9a01-2b3c4d5e6f70
    018f3a2b-7c1d-7e50-8b2c-3d4e5f607182
"""

import argparse
import re
import secrets
import sys
import threading
import time

_LOCK = threading.Lock()
_STATE = {"ts_ms": -1, "counter": 0}

# 合法 v7 文本形态（版本位=7，变体位=8/9/a/b）
_V7_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def format_uuid(value, upper=False):
    """128 位整数 -> 标准连字符文本。"""
    h = f"{value:032x}"
    text = f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
    return text.upper() if upper else text


def generate_uuid7():
    """生成一个 UUIDv7（128 位整数）。本进程内严格单调递增。"""
    now_ms = time.time_ns() // 1_000_000
    with _LOCK:
        if now_ms < _STATE["ts_ms"]:              # 时钟回拨保护
            now_ms = _STATE["ts_ms"]
        if now_ms == _STATE["ts_ms"]:
            counter = (_STATE["counter"] + 1) & 0x0FFF
            if counter == 0:                      # 12 位计数器溢出 -> 前移 1ms
                now_ms += 1
                counter = secrets.randbelow(1 << 12)
        else:
            counter = secrets.randbelow(1 << 12)
        _STATE["ts_ms"] = now_ms
        _STATE["counter"] = counter
    value = (now_ms & 0xFFFFFFFFFFFF) << 80       # 48 位 Unix 毫秒时间戳
    value |= 0x7 << 76                            # 版本号 7
    value |= counter << 64                        # rand_a = 单调计数器
    value |= 0b10 << 62                           # 变体位 10
    value |= secrets.randbits(62)                 # rand_b
    return value


def _selftest():
    # 1) 1000 个连续生成的 UUID：格式、版本、变体、严格单调递增
    values = [generate_uuid7() for _ in range(1000)]
    for v in values:
        assert (v >> 76) & 0xF == 7, "版本号不是 7"
        assert (v >> 62) & 0b11 == 0b10, "变体位不是 10"
    for prev, cur in zip(values, values[1:]):
        assert cur > prev, "字典序/时间序未单调递增"
    for v in values[:5]:
        assert _V7_RE.match(format_uuid(v)), f"文本形态不符合 v7: {format_uuid(v)}"
    # 2) 计数器溢出路径：同毫秒内计数器打满后仍需保持递增
    _STATE["ts_ms"] = time.time_ns() // 1_000_000
    _STATE["counter"] = 0x0FFE
    a = generate_uuid7()
    b = generate_uuid7()
    c = generate_uuid7()
    assert a < b < c, "计数器溢出路径未保持递增"
    print("selftest ok: 1000 个 v7 格式/版本/变体正确且严格单调递增；计数器溢出路径正常")
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        prog="uuid7-gen.py",
        description="RFC 9562 UUIDv7 生成器（毫秒时间戳有序，纯标准库）",
    )
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="生成数量（默认 1，须为正整数）")
    parser.add_argument("--upper", action="store_true", help="输出大写")
    parser.add_argument("--selftest", action="store_true", help="运行内置自测并退出")
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.count < 1:
        parser.error("-n 必须为正整数")
    for _ in range(args.count):
        print(format_uuid(generate_uuid7(), upper=args.upper))
    return 0


if __name__ == "__main__":
    sys.exit(main())
