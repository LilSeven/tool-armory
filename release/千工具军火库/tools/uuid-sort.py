#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""uuid-sort.py —— UUID 时序排序器（单文件，纯 Python 标准库）。

v1/v6/v7 按内嵌时间戳升序（各自折算为 Unix 微秒后统一比较）；
其他版本（v0/v2-v5/v8）与无法解析的文本按字典序，排在时序组之后。
排序稳定：键相同的保持输入相对顺序；重复项原样保留。

用法：
    python -I uuid-sort.py [UUID ...] [-f 列表文件] [-r] [--mark] [--selftest]

示例命令：
    python -I "K:/WorkAreaZcode/tool-armory/tools/uuid-sort.py" 018f3a2b-7c1d-7e4f-9a01-2b3c4d5e6f70 6ba7b810-9dad-11d1-80b4-00c04fd430c8
    python -I "K:/WorkAreaZcode/tool-armory/tools/uuid7-gen.py" -n 3 | python -I "K:/WorkAreaZcode/tool-armory/tools/uuid-sort.py" --mark

示例输出（--mark 时附注版本/时间）：
    6ba7b810-9dad-11d1-80b4-00c04fd430c8  # v1 2004-11-16T06:29:44.000Z
    018f3a2b-7c1d-7e4f-9a01-2b3c4d5e6f70  # v7 2026-11-02T08:00:00.123Z
"""

import argparse
import datetime
import re
import sys

# 1582-10-15 到 1970-01-01 (UTC) 的 100ns 单位数（v1/v6 格里高利时间戳基准）
GREGORIAN_OFFSET_100NS = 0x01B21DD213814000
_EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
_HEX = set("0123456789abcdefABCDEF")


def normalize(text):
    """去掉 urn:uuid: 前缀、花括号与首尾空白。"""
    t = text.strip()
    if t[:9].lower() == "urn:uuid:":
        t = t[9:]
    if len(t) >= 2 and t[0] == "{" and t[-1] == "}":
        t = t[1:-1].strip()
    return t


def to_canonical(text):
    """32 位无连字符或 8-4-4-4-12 形态 -> 小写标准形；否则返回 None。"""
    if len(text) == 32 and all(c in _HEX for c in text):
        h = text.lower()
        return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
    if (len(text) == 36 and text[8] == "-" and text[13] == "-"
            and text[18] == "-" and text[23] == "-"
            and all(c in _HEX for c in (text[:8] + text[9:13] + text[14:18]
                                        + text[19:23] + text[24:]))):
        return text.lower()
    return None


def unix_us(value, version):
    """内嵌时间戳统一折算为 Unix 微秒；无法折算返回 None。"""
    if version == 7:
        return (value >> 80) * 1_000
    if version == 1:
        low = (value >> 96) & 0xFFFFFFFF
        mid = (value >> 80) & 0xFFFF
        high = (value >> 64) & 0x0FFF
        ticks = (high << 48) | (mid << 32) | low
    elif version == 6:
        high = (value >> 96) & 0xFFFFFFFF
        mid = (value >> 80) & 0xFFFF
        low = (value >> 64) & 0x0FFF
        ticks = (high << 28) | (mid << 12) | low
    else:
        return None
    return (ticks - GREGORIAN_OFFSET_100NS) // 10


def _iso_utc(us):
    """Unix 微秒 -> ISO 8601 (UTC)；超出可表示范围返回 None。"""
    try:
        return (_EPOCH + datetime.timedelta(microseconds=us)
                ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None


def build_entries(tokens):
    """把 (行号, 原文) 列表转为可排序条目。key = (组, 时间微秒, 字符串)。"""
    entries = []
    for line_no, raw in tokens:
        text = normalize(raw)
        canon = to_canonical(text) if text else None
        if canon is None:
            entries.append({"key": (1, 0, raw), "text": raw, "note": "非法/无法识别"})
            continue
        value = int(canon.replace("-", ""), 16)
        version = (value >> 76) & 0xF
        us = unix_us(value, version)
        if us is not None:
            iso = _iso_utc(us)
            note = f"v{version} {iso}" if iso else f"v{version}（时间超出可表示范围）"
            entries.append({"key": (0, us, canon), "text": canon, "note": note})
        else:
            entries.append({"key": (1, 0, canon), "text": canon, "note": f"v{version}"})
    return entries


def collect_tokens(args):
    """收集 (行号, 原文)；来源优先级：--file > 位置参数 > stdin。"""
    tokens = []
    if args.file:
        with open(args.file, "r", encoding="utf-8", errors="replace") as fh:
            for line_no, line in enumerate(fh, 1):
                for tok in re.split(r"[\s,;]+", line.strip()):
                    if tok:
                        tokens.append((line_no, tok))
    if args.uuids:
        tokens.extend((i, u) for i, u in enumerate(args.uuids, 1))
    if not tokens and args.file is None:
        try:
            if not sys.stdin.isatty():
                for line_no, line in enumerate(sys.stdin, 1):
                    for tok in re.split(r"[\s,;]+", line.strip()):
                        if tok:
                            tokens.append((line_no, tok))
        except (AttributeError, OSError):
            pass
    return tokens


def _selftest():
    ts1 = 133200000000000000                    # 固定格里高利 ticks
    ts2 = ts1 + 10_000_000                      # 晚 1 秒
    us1 = (ts1 - GREGORIAN_OFFSET_100NS) // 10
    us2 = (ts2 - GREGORIAN_OFFSET_100NS) // 10
    seq, node = 0x100, 0x001122334455

    def synth_v1(ts):
        v = (ts & 0xFFFFFFFF) << 96
        v |= ((ts >> 32) & 0xFFFF) << 80
        v |= ((ts >> 48) & 0x0FFF) << 64
        v |= (1 << 76) | (0b10 << 62) | (seq << 48) | node
        return f"{v:032x}"

    def synth_v6(ts):
        v = ((ts >> 28) & 0xFFFFFFFF) << 96
        v |= ((ts >> 12) & 0xFFFF) << 80
        v |= (ts & 0x0FFF) << 64
        v |= (6 << 76) | (0b10 << 62) | (seq << 48) | node
        return f"{v:032x}"

    ms2 = us2 // 1000
    v7_raw = f"{(ms2 << 80) | (7 << 76) | (0xABC << 64) | (0b10 << 62) | 0x123456789ABC:032x}"
    v1_raw = synth_v1(ts1)
    v6_raw = synth_v6(ts1)
    v4_raw = "334a0d0f-6c1e-4c3d-9a1b-2f3e4d5c6b7a"
    bad_raw = "oops-not-a-uuid"

    def canon(h):
        return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"

    # 输入故意乱序：v7、v4、非法、v6、v1
    tokens = [(1, canon(v7_raw)), (2, v4_raw), (3, bad_raw),
              (4, canon(v6_raw)), (5, canon(v1_raw))]
    entries = build_entries(tokens)
    # v7 内嵌毫秒时间戳折算后的 Unix 微秒必须精确等于 us2（单位换算校验）
    v7_entry = next(e for e in entries if e["text"] == canon(v7_raw))
    assert v7_entry["key"][0] == 0 and v7_entry["key"][1] == us2, v7_entry
    out = [e["text"] for e in sorted(entries, key=lambda e: e["key"])]
    # 期望：v1/v6（同一微秒，按键内 canon 字典序）-> v7 -> 其他组（v4 与非法项按字典序）
    assert out[0] == min(canon(v1_raw), canon(v6_raw)), out
    assert out[1] == max(canon(v1_raw), canon(v6_raw)), out
    assert out[2] == canon(v7_raw), out
    assert out[3] == v4_raw.lower(), out
    assert out[4] == bad_raw, out
    # 反向：整体次序颠倒
    out_r = [e["text"] for e in sorted(build_entries(tokens), key=lambda e: e["key"],
                                       reverse=True)]
    assert out_r == list(reversed(out)), out_r
    # 时间排序与 Unix 微秒一致：v7 的时间应晚于 v1/v6
    assert us2 > us1
    print("selftest ok: v1/v6/v7 按内嵌时间戳排序、其余按字典序、-r 反向均正确")
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        prog="uuid-sort.py",
        description="v1/v6/v7 按内嵌时间戳排序，其他版本按字典序",
    )
    parser.add_argument("uuids", nargs="*",
                        help="要排序的 UUID（可多个；不带参数且未指定 --file 时从 stdin 读取）")
    parser.add_argument("-f", "--file", help="从文本文件读取 UUID 列表")
    parser.add_argument("-r", "--reverse", action="store_true", help="逆序输出")
    parser.add_argument("--mark", action="store_true",
                        help="行尾附注版本/时间（非法项标为 非法/无法识别）")
    parser.add_argument("--selftest", action="store_true", help="运行内置自测并退出")
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()

    tokens = collect_tokens(args)
    entries = build_entries(tokens)
    entries.sort(key=lambda e: e["key"], reverse=args.reverse)
    for e in entries:
        if args.mark:
            print(f"{e['text']}  # {e['note']}")
        else:
            print(e["text"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
