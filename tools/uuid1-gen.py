#!/usr/bin/env python3
"""UUIDv1 生成器 —— 生成基于时间戳 + MAC 的 UUIDv1（RFC 4122），并解读其时间/时钟序列/节点字段。

示例:
  python uuid1-gen.py                       # 生成 1 个并解读全部字段
  python uuid1-gen.py --count 5             # 批量 5 个
  python uuid1-gen.py --count 3 --local     # 同时显示本地时区时间
  python uuid1-gen.py --node AA:BB:CC:DD:EE:FF   # 用指定节点（伪造 MAC）生成
  python uuid1-gen.py --no-explain          # 只输出 UUID 本身
  python uuid1-gen.py selftest              # 内置自测
"""
import argparse
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone

# RFC 4122: UUIDv1 时间戳为 100ns 间隔，起点为改儒略历 1582-10-15 00:00:00 UTC
_GREGORIAN_OFFSET_100NS = 122192928000000000  # 1582-10-15 → 1970-01-01 的 100ns 数
_NODE_RE = re.compile(r"^([0-9a-fA-F]{1,2})[:\-]([0-9a-fA-F]{1,2})[:\-]([0-9a-fA-F]{1,2})"
                      r"[:\-]([0-9a-fA-F]{1,2})[:\-]([0-9a-fA-F]{1,2})[:\-]([0-9a-fA-F]{1,2})$")


def parse_node(s: str) -> int:
    """'AA:BB:CC:DD:EE:FF' / 'aa-bb-cc-dd-ee-ff' / 'aabbccddeeff' -> 48 位整数。"""
    s = s.strip()
    m = _NODE_RE.match(s)
    if m:
        return int("".join(g.zfill(2) for g in m.groups()), 16)
    if re.fullmatch(r"[0-9a-fA-F]{12}", s):
        return int(s, 16)
    raise ValueError(f"无效的节点地址: {s!r}（示例 AA:BB:CC:DD:EE:FF 或 12 位十六进制）")


def decode_v1(u: uuid.UUID) -> dict:
    """解读 UUIDv1 的字段。time/clock_seq/node 与标准库属性交叉可验。"""
    if u.variant != uuid.RFC_4122 or u.version != 1:
        raise ValueError(f"不是 RFC 4122 UUIDv1: {u}")
    t = u.time                                # 60 位时间戳（100ns，自 1582-10-15）
    unix_us = (t - _GREGORIAN_OFFSET_100NS) // 10  # 转 Unix 微秒
    dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=unix_us)
    node = u.node
    return {
        "timestamp_hex": "0x%015x" % t,
        "timestamp_100ns": t,
        "utc": dt,
        "unix_us": unix_us,
        "clock_seq": u.clock_seq,             # 14 位
        "node": node,
        "mac": "-".join("%02x" % (node >> s & 0xFF) for s in (40, 32, 24, 16, 8, 0)),
        "multicast": bool(node >> 40 & 0x01),  # 组播位=1 表示非真实 MAC（随机/伪造）
        "time_low": t & 0xFFFFFFFF,
        "time_mid": t >> 32 & 0xFFFF,
        "time_hi": t >> 48 & 0x0FFF,
    }


def gen_v1(node: int = None) -> uuid.UUID:
    return uuid.uuid1(node=node)


def explain(u: uuid.UUID, local: bool = False) -> str:
    d = decode_v1(u)
    lines = [
        f"uuid:       {u}",
        f"version:    {u.version} (time-based)",
        f"variant:    RFC 4122",
        f"timestamp:  {d['timestamp_hex']} (60bit, 100ns since 1582-10-15)",
        f"utc_time:   {d['utc'].isoformat().replace('+00:00', 'Z')}",
    ]
    if local:
        lines.append(f"local_time: {d['utc'].astimezone().isoformat()}")
    lines += [
        f"clock_seq:  0x%04x ({d['clock_seq']})" % d["clock_seq"],
        f"node/mac:   {d['mac']}" + ("  [multicast 位=1: 非真实网卡地址]" if d["multicast"] else ""),
    ]
    return "\n".join(lines)


def cmd_main(args) -> int:
    node = parse_node(args.node) if args.node else None
    if args.no_explain:
        for _ in range(args.count):
            print(gen_v1(node))
        return 0
    for i in range(args.count):
        if i:
            print()
        print(explain(gen_v1(node), local=args.local))
    return 0


def _selftest() -> int:
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        print(f"[{'PASS' if cond else 'FAIL'}] {name}")

    now = datetime.now(timezone.utc)

    # 1. 生成 + 全字段解读
    u = uuid.uuid1()
    d = decode_v1(u)
    check("version==1 且 variant==RFC_4122",
          u.version == 1 and u.variant == uuid.RFC_4122)
    check("解码 timestamp 与标准库 u.time 一致",
          d["timestamp_100ns"] == u.time and d["timestamp_hex"] == "0x%015x" % u.time)
    check("解码 clock_seq/node 与标准库一致",
          d["clock_seq"] == u.clock_seq and d["node"] == u.node)
    check("解码时间接近当前 UTC（±120s）",
          abs((d["utc"] - now).total_seconds()) < 120)
    check("MAC 与 uuid.getnode() 一致", d["node"] == uuid.getnode())
    check("真实网卡地址: 组播位=0", not d["multicast"])

    # 2. 本地时区换算正确性: 同一时刻 local=UTC+时区偏移
    loc = d["utc"].astimezone()
    check("时区换算（astimezone 偏移一致）",
          loc.utcoffset() == d["utc"].astimezone().utcoffset()
          and loc.replace(tzinfo=None) - loc.utcoffset() == d["utc"].replace(tzinfo=None))

    # 3. 时间单调性: 连续生成的 UUID 时间戳不回退
    ts = [uuid.uuid1().time for _ in range(100)]
    check("100 个连续 UUID 时间戳单调不回退", all(a <= b for a, b in zip(ts, ts[1:])))

    # 4. 指定节点生成
    n = parse_node("AA:BB:CC:DD:EE:FF")
    check("parse_node 冒号格式", n == 0xAABBCCDDEEFF)
    check("parse_node 连字符/无分隔格式",
          parse_node("aa-bb-cc-dd-ee-ff") == n and parse_node("aabbccddeeff") == n)
    u2 = uuid.uuid1(node=n)
    check("--node 生成使用指定节点", u2.node == n)
    try:
        parse_node("GG:BB:CC:DD:EE:FF")
        check("非法节点报错", False)
    except ValueError:
        check("非法节点报错", True)

    # 5. 解码器对任意字段组合自洽: 由位重组 UUID 再解码应还原
    # RFC 4122 整数布局(MSB 在前): time_low<<96 | time_mid<<80 | (ver<<12|time_hi)<<64
    #                            | clock_seq(含变体位)<<48 | node
    t = 0x1EC9414C232AB00
    cs = 0x33C8
    node_bits = 0x9E6BDECDEC75
    raw = ((t & 0xFFFFFFFF) << 96) | (((t >> 32) & 0xFFFF) << 80) \
        | ((1 << 12 | (t >> 48)) << 64) | ((cs | 0x8000) << 48) | node_bits
    u3 = uuid.UUID(int=raw)
    check("手工位重组得到 RFC 9562 示例形态",
          str(u3) == "c232ab00-9414-11ec-b3c8-9e6bdecdec75")
    d3 = decode_v1(u3)
    check("解码手工位重组: time/clock_seq/node 还原",
          d3["timestamp_100ns"] == t and d3["clock_seq"] == cs and d3["node"] == node_bits)
    want_dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
        microseconds=(t - _GREGORIAN_OFFSET_100NS) // 10)
    check("手工位重组时间换算", d3["utc"] == want_dt)

    # 6. 非法输入: 非 v1 UUID 拒绝解码
    try:
        decode_v1(uuid.uuid4())
        check("v4 UUID 拒绝按 v1 解码", False)
    except ValueError:
        check("v4 UUID 拒绝按 v1 解码", True)

    failed = [n2 for n2, ok2 in checks if not ok2]
    print(f"\nselftest: {len(checks) - len(failed)}/{len(checks)} 项通过")
    if failed:
        print("失败项:", "; ".join(failed))
        return 1
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="uuid1-gen.py",
        description="生成基于时间戳+MAC 的 UUIDv1，并解读其时间字段。")
    p.add_argument("--count", "-n", type=int, default=1, help="生成数量（默认 1，上限 10000）")
    p.add_argument("--node", help="指定 48 位节点地址（如 AA:BB:CC:DD:EE:FF）")
    p.add_argument("--local", action="store_true", help="同时显示本地时区时间")
    p.add_argument("--no-explain", action="store_true", help="只输出 UUID 字符串")
    p.add_argument("cmd", nargs="?", choices=["selftest"], help=argparse.SUPPRESS)
    return p


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    if args.cmd == "selftest":
        return _selftest()
    if args.count < 1 or args.count > 10000:
        args.error("count 取值 1..10000")
    if args.node:
        try:
            parse_node(args.node)
        except ValueError as e:
            args.error(str(e))
    try:
        return cmd_main(args)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
