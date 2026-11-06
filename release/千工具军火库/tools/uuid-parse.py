#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""uuid-parse.py —— UUID 结构解析器（单文件，纯 Python 标准库）。

解析任意 UUID 文本（标准连字符 / 32 位无连字符 / {花括号} / urn:uuid: 前缀）的
版本号与变体；对 v1/v6 解出 60 位格里高利历时间戳（100ns，折算 Unix 微秒并给出
UTC 可读时间）、时钟序列与节点地址（MAC，含多播位提示）；对 v7 解出 Unix 毫秒时间戳。

用法：
    python -I uuid-parse.py <UUID> [更多 UUID ...]
    cat uuid列表.txt | python -I uuid-parse.py

示例命令：
    python -I "K:/WorkAreaZcode/tool-armory/tools/uuid-parse.py" 018f3a2b-7c1d-7e4f-9a01-2b3c4d5e6f70
    python -I "K:/WorkAreaZcode/tool-armory/tools/uuid-parse.py" --json "urn:uuid:6ba7b810-9dad-11d1-80b4-00c04fd430c8"

示例输出：
    UUID   : 018f3a2b-7c1d-7e4f-9a01-2b3c4d5e6f70
    版本   : 7  基于时间·Unix 毫秒（v7）
    变体   : RFC 9562/4122
    时间戳 : 2026-11-02T08:00:00.123Z
"""

import argparse
import datetime
import json
import re
import sys

# 1582-10-15 00:00 到 1970-01-01 00:00 (UTC) 之间的 100ns 单位数
GREGORIAN_OFFSET_100NS = 0x01B21DD213814000
_EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
_HEX = set("0123456789abcdefABCDEF")

VERSION_NAMES = {
    0: "特殊（NIL/占位）",
    1: "基于时间·格里高利 100ns（v1）",
    2: "DCE 安全（v2）",
    3: "MD5 名字哈希（v3）",
    4: "随机（v4）",
    5: "SHA-1 名字哈希（v5）",
    6: "基于时间·重排·格里高利 100ns（v6）",
    7: "基于时间·Unix 毫秒（v7）",
    8: "自定义（v8）",
}


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


def variant_of(value):
    """按最高 3 位变体位判断。返回 (描述, 编号)。"""
    top3 = (value >> 61) & 0b111
    if top3 >> 2 == 0:
        return "NCS（向后兼容）", 0
    if top3 >> 1 == 0b10:
        return "RFC 9562/4122", 1
    if top3 == 0b110:
        return "Microsoft（GUID）", 2
    return "保留（未来用途）", 3


def gregorian_ticks(value, version):
    """v1/v6 的 60 位格里高利时间戳（100ns 单位）；其他版本返回 None。"""
    if version == 1:
        low = (value >> 96) & 0xFFFFFFFF
        mid = (value >> 80) & 0xFFFF
        high = (value >> 64) & 0x0FFF
        return (high << 48) | (mid << 32) | low
    if version == 6:
        high = (value >> 96) & 0xFFFFFFFF
        mid = (value >> 80) & 0xFFFF
        low = (value >> 64) & 0x0FFF
        return (high << 28) | (mid << 12) | low
    return None


def unix_us(value, version):
    """内嵌时间戳统一折算为 Unix 微秒；无法折算返回 None。"""
    if version == 7:
        return (value >> 80) * 1_000
    ticks = gregorian_ticks(value, version)
    if ticks is None:
        return None
    return (ticks - GREGORIAN_OFFSET_100NS) // 10


def describe_error(text):
    """给出无法解析的具体原因。"""
    if not text:
        return "空输入"
    if len(text) not in (32, 36):
        return f"长度不符：应为 36（标准形）或 32（无连字符），实际 {len(text)}"
    if len(text) == 32:
        bad = sorted({c for c in text if c not in _HEX})
        return f"含非十六进制字符：{'、'.join(repr(c) for c in bad[:8])}"
    if not (text[8] == "-" and text[13] == "-" and text[18] == "-" and text[23] == "-"):
        return "连字符位置错误：应为 8-4-4-4-12 分段"
    groups = (text[:8], text[9:13], text[14:18], text[19:23], text[24:])
    for idx, part in enumerate(groups, 1):
        bad = sorted({c for c in part if c not in _HEX})
        if bad:
            return f"第 {idx} 段含非十六进制字符：{'、'.join(repr(c) for c in bad[:8])}"
    return "格式无法识别"


def parse_uuid(text):
    """解析一个 UUID 文本。成功返回 (信息字典, None)，失败返回 (None, 原因)。"""
    t = normalize(text)
    canon = to_canonical(t)
    if canon is None:
        return None, describe_error(t)
    value = int(canon.replace("-", ""), 16)
    version = (value >> 76) & 0xF
    variant_desc, variant_id = variant_of(value)
    info = {
        "uuid": canon,
        "version": version,
        "version_name": VERSION_NAMES.get(version, "未知"),
        "variant": variant_desc,
        "variant_id": variant_id,
    }
    if value == 0:
        info["special"] = "NIL UUID（全零）"
    elif value == (1 << 128) - 1:
        info["special"] = "MAX UUID（全一）"
    us = unix_us(value, version)
    if us is not None:
        info["unix_us"] = us
        try:
            info["time_utc"] = (_EPOCH + datetime.timedelta(microseconds=us)
                                ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            info["time_utc"] = None
    if version == 1:
        info["time_field"] = "time_low+time_mid+time_hi（60 位格里高利 100ns）"
    elif version == 6:
        info["time_field"] = "time_high+time_mid+time_low（60 位格里高利 100ns）"
    elif version == 7:
        info["time_field"] = f"unix_ts_ms = {value >> 80}"
    if version in (1, 6):
        seq = (value >> 48) & 0x3FFF
        node = value & 0xFFFFFFFFFFFF
        info["clock_seq"] = seq
        info["node"] = ":".join(f"{(node >> s) & 0xFF:02x}"
                                for s in (40, 32, 24, 16, 8, 0))
        info["node_is_random"] = bool(node & (1 << 40))
    return info, None


def render(info):
    lines = [
        f"UUID   : {info['uuid']}",
        f"版本   : {info['version']}  {info['version_name']}",
        f"变体   : {info['variant']}",
    ]
    if "special" in info:
        lines.append(f"特殊值 : {info['special']}")
    if "time_utc" in info:
        shown = info["time_utc"] or "超出 datetime 可表示范围"
        lines.append(f"时间戳 : {shown}")
    if "time_field" in info:
        lines.append(f"时间字段: {info['time_field']}")
    if "clock_seq" in info:
        lines.append(f"时钟序列: 0x{info['clock_seq']:04x}（{info['clock_seq']}）")
        kind = ("随机节点（多播位置位，非全局 MAC）" if info["node_is_random"]
                else "可能来自真实 MAC（多播位清零）")
        lines.append(f"节点 MAC: {info['node']}（{kind}）")
    return "\n".join(lines)


def _selftest():
    ts100 = 133200000000000000            # 固定格里高利 ticks（约 2004 年）
    expected_us = (ts100 - GREGORIAN_OFFSET_100NS) // 10
    seq, node = 0x1234, 0x001122334455

    def synth_v1(ts, seq_, node_):
        v = (ts & 0xFFFFFFFF) << 96
        v |= ((ts >> 32) & 0xFFFF) << 80
        v |= ((ts >> 48) & 0x0FFF) << 64
        v |= (1 << 76) | (0b10 << 62) | ((seq_ & 0x3FFF) << 48) | (node_ & 0xFFFFFFFFFFFF)
        return v

    def synth_v6(ts, seq_, node_):
        v = ((ts >> 28) & 0xFFFFFFFF) << 96
        v |= ((ts >> 12) & 0xFFFF) << 80
        v |= (ts & 0x0FFF) << 64
        v |= (6 << 76) | (0b10 << 62) | ((seq_ & 0x3FFF) << 48) | (node_ & 0xFFFFFFFFFFFF)
        return v

    def fmt(v):
        h = f"{v:032x}"
        return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"

    # v1 / v6：版本、变体、时间戳折算、时钟序列、节点 MAC
    for ver, synth in ((1, synth_v1), (6, synth_v6)):
        raw = fmt(synth(ts100, seq, node))
        info, err = parse_uuid(raw)
        assert err is None, err
        assert info["version"] == ver, info
        assert info["variant_id"] == 1, info
        assert gregorian_ticks(int(raw.replace('-', ''), 16), ver) == ts100
        assert info["unix_us"] == expected_us, info
        assert info["clock_seq"] == seq, info
        assert info["node"] == "00:11:22:33:44:55", info
        assert info["node_is_random"] is False, info
    # 同一时刻的 v1 与 v6 折算出的 Unix 微秒一致
    i1, e1 = parse_uuid(fmt(synth_v1(ts100, seq, node)))
    i6, e6 = parse_uuid(fmt(synth_v6(ts100, seq, node)))
    assert e1 is None and e6 is None and i1["unix_us"] == i6["unix_us"]

    # v7：毫秒时间戳
    ms = 1_700_000_000_123
    v7 = (ms << 80) | (7 << 76) | (0xABC << 64) | (0b10 << 62) | 0x123456789ABC
    info, err = parse_uuid(fmt(v7))
    assert err is None and info["version"] == 7, info
    assert info["unix_us"] == ms * 1000, info

    # 四种书写形态等价
    base = fmt(synth_v1(ts100, seq, node))
    forms = [base, "{" + base + "}", "urn:uuid:" + base, base.replace("-", "")]
    canon_set = {parse_uuid(f)[0]["uuid"] for f in forms}
    assert canon_set == {base}, canon_set

    # NIL / MAX 特殊值
    info, _ = parse_uuid("00000000-0000-0000-0000-000000000000")
    assert info["special"] == "NIL UUID（全零）"
    info, _ = parse_uuid("ffffffff-ffff-ffff-ffff-ffffffffffff")
    assert info["special"] == "MAX UUID（全一）"

    # 非法输入必须给出原因
    for bad in ("not-a-uuid", "12345678-1234-1234-1234-123456789abc0",
                "g2345678-1234-1234-1234-123456789abc", ""):
        info, err = parse_uuid(bad)
        assert info is None and err, (bad, err)

    print("selftest ok: v1/v6/v7 时间戳与时钟序列、节点解析正确；"
          "四种书写形态等价；NIL/MAX 识别正常；非法输入均给出原因")
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        prog="uuid-parse.py",
        description="解析 UUID 的版本、变体、时间戳（v1/v6/v7）与节点 MAC 等字段",
    )
    parser.add_argument("uuids", nargs="*",
                        help="要解析的 UUID 文本（可多个；不带参数时从 stdin 读取）")
    parser.add_argument("--json", action="store_true", help="以 JSON 数组输出")
    parser.add_argument("--selftest", action="store_true", help="运行内置自测并退出")
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()

    items = list(args.uuids)
    if not items:
        try:
            if not sys.stdin.isatty():
                items = [tok for tok in re.split(r"[\s,;]+", sys.stdin.read()) if tok]
        except (AttributeError, OSError):
            pass
    if not items:
        parser.print_help()
        return 2

    results = []
    for raw in items:
        info, err = parse_uuid(raw)
        results.append({"input": raw, "error": err} if err is not None else info)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for idx, res in enumerate(results):
            if idx:
                print("-" * 46)
            if "error" in res:
                print(f"✗ 无法解析 {res['input']!r}：{res['error']}")
            else:
                print(render(res))
    return 0  # 个别解析失败会逐条报告，不影响退出码


if __name__ == "__main__":
    sys.exit(main())
