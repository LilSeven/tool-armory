#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""雪花 ID 工具：生成与解析 Twitter 风格雪花 ID（毫秒时间 + 机器号 + 序列）。

位布局（63 位整数）：
    [41 位] 毫秒时间差（相对 epoch，默认 Twitter epoch 1288834974657）
    [10 位] 机器号   0..1023
    [12 位] 序列号   0..4095（同一毫秒内递增；溢出则进位到下一毫秒；
             时钟回拨时沿用上一时间戳，保证单调）

示例命令：
    python snowflake-id.py gen -n 3 -m 1
    python snowflake-id.py make --time 1700000000000 -m 1 --seq 2
    python snowflake-id.py parse 1893456789012345678
    python snowflake-id.py gen -n 2 -m 7 --epoch 0
    python snowflake-id.py selftest

退出码：0 成功；2 输入或参数非法。
"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone

TS_BITS = 41
MACHINE_BITS = 10
SEQ_BITS = 12
MACHINE_MAX = (1 << MACHINE_BITS) - 1
SEQ_MAX = (1 << SEQ_BITS) - 1
TOTAL_BITS = TS_BITS + MACHINE_BITS + SEQ_BITS  # 63
DEFAULT_EPOCH = 1288834974657  # Twitter epoch: 2010-11-04T01:42:54.657Z
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def now_ms() -> int:
    return int(time.time() * 1000)


def make_id(time_ms: int, machine: int, seq: int, epoch: int = DEFAULT_EPOCH) -> int:
    """由字段构造雪花 ID：delta(41) << 22 | machine(10) << 12 | seq(12)。"""
    if not 0 <= machine <= MACHINE_MAX:
        raise ValueError("machine must be in [0, %d], got %d" % (MACHINE_MAX, machine))
    if not 0 <= seq <= SEQ_MAX:
        raise ValueError("seq must be in [0, %d], got %d" % (SEQ_MAX, seq))
    delta = time_ms - epoch
    if not 0 <= delta < (1 << TS_BITS):
        raise ValueError(
            "time_ms %d is out of range for epoch %d (delta must be in [0, 2^%d))" %
            (time_ms, epoch, TS_BITS))
    return (delta << (MACHINE_BITS + SEQ_BITS)) | (machine << SEQ_BITS) | seq


def parse_id(snowflake: int, epoch: int = DEFAULT_EPOCH):
    """雪花 ID -> (unix 毫秒时间戳, 机器号, 序列号)。"""
    if not 0 <= snowflake < (1 << TOTAL_BITS):
        raise ValueError("snowflake id must be in [0, 2^%d), got %d" % (TOTAL_BITS, snowflake))
    delta = snowflake >> (MACHINE_BITS + SEQ_BITS)
    machine = (snowflake >> SEQ_BITS) & MACHINE_MAX
    seq = snowflake & SEQ_MAX
    return epoch + delta, machine, seq


def ms_to_iso(ms: int) -> str:
    try:
        dt = _UNIX_EPOCH + timedelta(milliseconds=ms)
    except (OverflowError, OSError):
        return "out-of-datetime-range"
    return "%04d-%02d-%02dT%02d:%02d:%02d.%03dZ" % (
        dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, ms % 1000)


class SnowflakeGen:
    """单进程单调生成器：同毫秒序列号递增，溢出进位下一毫秒，时钟回拨沿用上一毫秒。"""

    def __init__(self, machine: int, epoch: int = DEFAULT_EPOCH) -> None:
        if not 0 <= machine <= MACHINE_MAX:
            raise ValueError("machine must be in [0, %d], got %d" % (MACHINE_MAX, machine))
        self.machine = machine
        self.epoch = epoch
        self._last_ts = -1
        self._seq = 0

    def next(self) -> int:
        ts = now_ms()
        if ts < self._last_ts:
            ts = self._last_ts
        if ts == self._last_ts:
            self._seq += 1
            if self._seq > SEQ_MAX:
                self._seq = 0
                ts += 1
        else:
            self._seq = 0
        self._last_ts = ts
        return make_id(ts, self.machine, self._seq, self.epoch)


def cmd_gen(args) -> int:
    try:
        gen = SnowflakeGen(args.machine, args.epoch)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    for _ in range(args.n):
        print(gen.next())
    return 0


def cmd_make(args) -> int:
    try:
        print(make_id(args.time, args.machine, args.seq, args.epoch))
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    return 0


def cmd_parse(args) -> int:
    try:
        for raw in args.ids:
            sid = int(raw, 10)
            unix_ms, machine, seq = parse_id(sid, args.epoch)
            print("%d -> unix_ms=%d iso=%s machine=%d seq=%d" %
                  (sid, unix_ms, ms_to_iso(unix_ms), machine, seq))
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    return 0


def cmd_selftest(_args) -> int:
    checks = []

    def check(name, cond):
        checks.append(bool(cond))
        print(("ok:   " if cond else "FAIL: ") + name)

    fixed = make_id(1700000000000, 1, 2)
    unix_ms, machine, seq = parse_id(fixed)
    check("make/parse roundtrip", (unix_ms, machine, seq) == (1700000000000, 1, 2))
    check("id fits in 63 bits", 0 <= fixed < (1 << TOTAL_BITS))
    check("iso format", ms_to_iso(1700000000000) == "2023-11-14T22:13:20.000Z")

    fixed2 = make_id(1700000000000, 1, 2, epoch=0)
    check("custom epoch roundtrip", parse_id(fixed2, epoch=0) == (1700000000000, 1, 2))
    check("epoch changes id", fixed2 != fixed)

    gen = SnowflakeGen(7)
    ids = [gen.next() for _ in range(20)]
    check("gen strictly increasing", all(b > a for a, b in zip(ids, ids[1:])))
    parsed = [parse_id(i) for i in ids]
    check("gen machine consistent", all(p[1] == 7 for p in parsed))
    check("gen time monotonic", all(b[0] >= a[0] for a, b in zip(parsed, parsed[1:])))
    check("first gen seq is 0", parsed[0][2] == 0)

    gen2 = SnowflakeGen(0)
    gen2._last_ts = now_ms()  # 让下一次调用落在“同一毫秒”，触发序列溢出分支
    gen2._seq = SEQ_MAX
    sid = gen2.next()
    rolled = parse_id(sid)
    check("seq overflow rolls to next ms",
          rolled[1] == 0 and rolled[2] == 0 and rolled[0] == gen2._last_ts)

    gen3 = SnowflakeGen(0)
    gen3._last_ts = 2000000000000  # 模拟时钟回拨
    back = parse_id(gen3.next())
    check("clock rollback keeps monotonic ts", back[0] == 2000000000000)

    def raises(fn):
        try:
            fn()
        except ValueError:
            return True
        return False

    check("machine 1024 rejected", raises(lambda: make_id(1700000000000, 1024, 0)))
    check("seq 4096 rejected", raises(lambda: make_id(1700000000000, 0, 4096)))
    check("time before epoch rejected", raises(lambda: make_id(0, 0, 0)))
    check("negative id rejected", raises(lambda: parse_id(-1)))
    check("id >= 2^63 rejected", raises(lambda: parse_id(1 << 63)))

    total = len(checks)
    if all(checks):
        print("selftest ok (%d/%d checks)" % (total, total))
        return 0
    print("selftest FAILED (%d/%d checks failed)" % (checks.count(False), total))
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="snowflake-id.py",
        description="生成与解析 Twitter 风格雪花 ID（毫秒时间 + 机器号 + 序列）",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    pg = sub.add_parser("gen", help="生成雪花 ID")
    pg.add_argument("-n", type=int, default=1, help="生成数量（默认 1）")
    pg.add_argument("-m", "--machine", type=int, default=0, help="机器号 0..1023（默认 0）")
    pg.add_argument("--epoch", type=int, default=DEFAULT_EPOCH, help="自定义纪元毫秒")
    pg.set_defaults(func=cmd_gen)
    pm = sub.add_parser("make", help="由字段构造雪花 ID（确定性）")
    pm.add_argument("--time", type=int, required=True, help="unix 毫秒时间戳")
    pm.add_argument("-m", "--machine", type=int, default=0, help="机器号 0..1023")
    pm.add_argument("--seq", type=int, default=0, help="序列号 0..4095")
    pm.add_argument("--epoch", type=int, default=DEFAULT_EPOCH, help="自定义纪元毫秒")
    pm.set_defaults(func=cmd_make)
    pp = sub.add_parser("parse", help="解析雪花 ID")
    pp.add_argument("ids", nargs="+", help="一个或多个雪花 ID")
    pp.add_argument("--epoch", type=int, default=DEFAULT_EPOCH, help="自定义纪元毫秒")
    pp.set_defaults(func=cmd_parse)
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
