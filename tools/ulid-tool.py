#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ULID 生成/解析工具：48 位毫秒时间戳 + 80 位随机数，26 字符 Crockford Base32。

用途：
    gen       生成 ULID（默认当前时间；--ts 指定毫秒时间戳，--at 指定 ISO 时间；
              -n 批量）。同一毫秒内自动递增随机部分，保证单调递增。
    parse     解析 ULID：毫秒时间戳、ISO 时间、随机数。
    sort      批量按时间（即数值）升序排序输出（参数或 stdin 传入均可）。
    check     校验 ULID 是否合法（合法退出码 0，非法 1）。
    selftest  运行内置自测。

编码规则：Crockford Base32 字母表 0123456789ABCDEFGHJKMNPQRSTVWXYZ（不含 I/L/O/U）；
时间戳 10 字符（首字符必为 0-7）+ 随机数 16 字符 = 26 字符；解码容忍小写与 I/L->1、O->0。

示例命令：
    python ulid-tool.py gen -n 3
    python ulid-tool.py gen --ts 1600000000000
    python ulid-tool.py gen --at 2026-11-02T12:00:00Z
    python ulid-tool.py parse 01ARZ3NDEKTSV4RRFFQ69G5FAV
    python ulid-tool.py sort 01ARZ3NDEKTSV4RRFFQ69G5FAV 01ARZ3NDEKTSV4RRFFQ69G5FAW
    python ulid-tool.py gen -n 5 | python ulid-tool.py sort
    python ulid-tool.py selftest

退出码：0 成功；1 check 判定非法；2 输入或参数非法。
"""

import argparse
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
LEN = 26
TS_BITS = 48
RAND_BITS = 80
_TS_MAX = 1 << TS_BITS
_RAND_MAX = 1 << RAND_BITS
_FIX = str.maketrans({"I": "1", "L": "1", "O": "0", "i": "1", "l": "1", "o": "0"})
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def b32_encode(value: int, length: int) -> str:
    """非负整数 -> 定长 Crockford Base32（高位补 0）。"""
    if value < 0 or value >= 1 << (5 * length):
        raise ValueError("value out of range for %d chars" % length)
    chars = []
    for shift in range((length - 1) * 5, -1, -5):
        chars.append(ALPHABET[(value >> shift) & 0x1F])
    return "".join(chars)


def decode(text: str) -> int:
    """ULID 字符串 -> 128 位整数（高 48 位时间戳，低 80 位随机数）。"""
    s = text.strip().replace("-", "").replace(" ", "").upper().translate(_FIX)
    if len(s) != LEN:
        raise ValueError("ULID must be %d characters, got %d" % (LEN, len(s)))
    value = 0
    for ch in s:
        idx = ALPHABET.find(ch)
        if idx < 0:
            raise ValueError("invalid ULID character %r (Crockford Base32 expected)" % ch)
        value = (value << 5) | idx
    if (value >> RAND_BITS) >= _TS_MAX:
        raise ValueError("ULID timestamp overflow (first character must be 0-7)")
    return value


def fields(value: int):
    """128 位整数 -> (毫秒时间戳, 随机数)。"""
    return value >> RAND_BITS, value & (_RAND_MAX - 1)


def encode_from_fields(ts_ms: int, rand: int) -> str:
    if not 0 <= ts_ms < _TS_MAX:
        raise ValueError("timestamp must be in [0, 2^48), got %d" % ts_ms)
    if not 0 <= rand < _RAND_MAX:
        raise ValueError("random part out of range: %d" % rand)
    return b32_encode((ts_ms << RAND_BITS) | rand, LEN)


def ms_to_iso(ms: int) -> str:
    try:
        dt = _UNIX_EPOCH + timedelta(milliseconds=ms)
    except (OverflowError, OSError):
        return "out-of-datetime-range"
    return "%04d-%02d-%02dT%02d:%02d:%02d.%03dZ" % (
        dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, ms % 1000)


def iso_to_ms(text: str) -> int:
    s = text.strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt - _UNIX_EPOCH) // timedelta(milliseconds=1)


class MonotonicULID:
    """同毫秒内随机部分 +1，保证同进程生成的 ULID 单调递增。"""

    def __init__(self) -> None:
        self._last_ts = -1
        self._last_rand = -1

    def next(self, ts_ms=None) -> str:
        if ts_ms is None:
            ts_ms = int(time.time() * 1000)
        if ts_ms < self._last_ts:
            ts_ms = self._last_ts  # 时钟回拨：沿用上一时间戳
        if ts_ms == self._last_ts:
            rand = self._last_rand + 1
            if rand >= _RAND_MAX:
                ts_ms += 1
                rand = secrets.randbits(RAND_BITS)
        else:
            rand = secrets.randbits(RAND_BITS)
        self._last_ts, self._last_rand = ts_ms, rand
        return encode_from_fields(ts_ms, rand)


def sort_ulids(items):
    """解析后按数值（即时间）升序排序，输出规范大写形式。"""
    return [b32_encode(v, LEN) for v in sorted(decode(x) for x in items)]


def cmd_gen(args) -> int:
    try:
        ts = args.ts
        if args.ts is not None and args.at is not None:
            raise ValueError("--ts and --at are mutually exclusive")
        if args.at is not None:
            ts = iso_to_ms(args.at)
        gen = MonotonicULID()
        out = [gen.next(ts) for _ in range(args.n)]
    except (ValueError, OverflowError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    print("\n".join(out))
    return 0


def cmd_parse(args) -> int:
    try:
        for raw in args.ulids:
            ts, rand = fields(decode(raw))
            print("%s -> ts_ms=%d iso=%s rand=0x%020x" % (raw.strip(), ts, ms_to_iso(ts), rand))
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    return 0


def cmd_sort(args) -> int:
    items = args.ulids if args.ulids else sys.stdin.read().split()
    if not items:
        print("error: no ULIDs given (pass as arguments or via stdin)", file=sys.stderr)
        return 2
    try:
        out = sort_ulids(items)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    print("\n".join(out))
    return 0


def cmd_check(args) -> int:
    try:
        decode(args.ulid)
    except ValueError as exc:
        print("INVALID: %s" % exc)
        return 1
    print("VALID")
    return 0


def cmd_selftest(_args) -> int:
    checks = []

    def check(name, cond):
        checks.append(bool(cond))
        print(("ok:   " if cond else "FAIL: ") + name)

    ts0 = 1600000000000
    u1 = MonotonicULID().next(ts0)
    v1 = decode(u1)
    t1, r1 = fields(v1)
    check("fixed-ts roundtrip", t1 == ts0 and 0 <= r1 < _RAND_MAX)
    check("canonical form (26 chars, uppercase, Crockford)",
          len(u1) == LEN and u1 == u1.upper() and set(u1) <= set(ALPHABET))
    check("first char encodes 48-bit ts (0-7)", ALPHABET.find(u1[0]) < 8)

    gen = MonotonicULID()
    a = decode(gen.next(ts0))
    b = decode(gen.next(ts0))
    c = decode(gen.next(ts0 + 1))
    check("same-ms monotonic", b > a)
    check("next-ms monotonic", c > b)

    batch = [MonotonicULID().next(ts) for ts in (1600000000005, 1600000000001, 1600000000003)]
    sorted_out = sort_ulids(list(reversed(batch)))
    tss = [fields(decode(x))[0] for x in sorted_out]
    check("sort ascending by time", tss == sorted(tss) and len(set(tss)) == 3)

    noisy = u1.lower().replace("0", "o").replace("1", "i")
    check("case / i-l-o tolerant decode", decode(noisy) == v1)
    check("hyphenated decode tolerated", decode("-".join([u1[:4], u1[4:]])) == v1)

    def raises(fn):
        try:
            fn()
        except ValueError:
            return True
        return False

    check("27 chars rejected", raises(lambda: decode("0" * 27)))
    check("letter U rejected", raises(lambda: decode("0" * 25 + "U")))
    overflow = b32_encode(1 << 128, LEN)  # ts = 2^48 -> 首字符 8
    check("timestamp overflow rejected", raises(lambda: decode(overflow)))
    check("negative ts rejected", raises(lambda: encode_from_fields(-1, 0)))
    check("iso roundtrip", iso_to_ms(ms_to_iso(ts0)) == ts0)

    total = len(checks)
    if all(checks):
        print("selftest ok (%d/%d checks)" % (total, total))
        return 0
    print("selftest FAILED (%d/%d checks failed)" % (checks.count(False), total))
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ulid-tool.py",
        description="生成/解析 ULID（毫秒时间戳 + Crockford Base32），支持批量排序",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    pg = sub.add_parser("gen", help="生成 ULID")
    pg.add_argument("-n", type=int, default=1, help="生成数量（默认 1）")
    pg.add_argument("--ts", type=int, default=None, help="指定毫秒时间戳（默认当前时间）")
    pg.add_argument("--at", default=None, help="指定 ISO 时间（如 2026-11-02T12:00:00Z）")
    pg.set_defaults(func=cmd_gen)
    pp = sub.add_parser("parse", help="解析 ULID")
    pp.add_argument("ulids", nargs="+")
    pp.set_defaults(func=cmd_parse)
    po = sub.add_parser("sort", help="按时间升序排序（参数或 stdin）")
    po.add_argument("ulids", nargs="*")
    po.set_defaults(func=cmd_sort)
    pc = sub.add_parser("check", help="校验 ULID 合法性")
    pc.add_argument("ulid")
    pc.set_defaults(func=cmd_check)
    pt = sub.add_parser("selftest", help="运行内置自测")
    pt.set_defaults(func=cmd_selftest)
    return p


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if getattr(args, "n", 1) < 1 or getattr(args, "n", 1) > 100000:
            raise ValueError("-n must be in [1, 100000]")
        return args.func(args)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
