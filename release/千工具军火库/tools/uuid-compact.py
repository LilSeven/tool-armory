#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UUID 紧凑编码：标准 UUID、无连字符 hex、Crockford Base32 紧凑形式互相转换。

用途：
    enc       标准 UUID -> 无连字符 32 位 hex + 26 字符 Crockford Base32。
    dec       hex / Crockford Base32 / 标准写法（含 {} 与 urn:uuid: 前缀）-> 标准 UUID，
              默认自动识别（--format hex|b32|uuid 可强制指定）。
    selftest  运行内置自测（安全示例输入，验证三种形式往返一致）。

Crockford Base32 字母表：0123456789ABCDEFGHJKMNPQRSTVWXYZ（不含 I/L/O/U）；
解码时 I/L 视作 1、O 视作 0，忽略连字符与空格，数值必须 < 2^128。

示例命令：
    python uuid-compact.py enc 3d813cbb-47fb-32ba-91df-831e1593ac29
    python uuid-compact.py dec 3d813cbb47fb32ba91df831e1593ac29
    python uuid-compact.py dec 0Y6M7GCHA7M9Q8BN5GB1W8YZQY
    python uuid-compact.py dec "0y6m-7gch" --format b32
    python uuid-compact.py selftest

退出码：0 成功；2 输入或参数非法。
"""

import argparse
import sys
import uuid as _uuid

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_HEX_DIGITS = set("0123456789abcdefABCDEF")
# Crockford 容错：I/L -> 1，O -> 0（U 直接拒绝）
_FIX = str.maketrans({"I": "1", "L": "1", "O": "0", "i": "1", "l": "1", "o": "0"})


def b32_encode(value: int, length: int) -> str:
    """把非负整数编码为定长 Crockford Base32（高位补 0）。"""
    if value < 0:
        raise ValueError("value must be non-negative")
    if value >= 1 << (5 * length):
        raise ValueError("value does not fit in %d Crockford Base32 chars" % length)
    chars = []
    for shift in range((length - 1) * 5, -1, -5):
        chars.append(ALPHABET[(value >> shift) & 0x1F])
    return "".join(chars)


def b32_decode(text: str) -> int:
    """解码 Crockford Base32（容忍连字符/空格/大小写，I/L->1、O->0），返回整数。"""
    cleaned = text.replace("-", "").replace(" ", "").upper().translate(_FIX)
    if not cleaned:
        raise ValueError("empty Crockford Base32 string")
    if "U" in cleaned:
        raise ValueError("letter U is not valid in Crockford Base32")
    value = 0
    for ch in cleaned:
        idx = ALPHABET.find(ch)
        if idx < 0:
            raise ValueError("invalid Crockford Base32 character: %r" % ch)
        value = (value << 5) | idx
    return value


def _to_compact(text: str) -> str:
    s = text.strip()
    if s.lower().startswith("urn:uuid:"):
        s = s[9:]
    return s.strip("{}[]").replace("-", "")


def _from_crockford(text: str) -> _uuid.UUID:
    value = b32_decode(text)
    if value >= 1 << 128:
        raise ValueError("Crockford Base32 value exceeds 128 bits (max 26 chars)")
    return _uuid.UUID(int=value)


def parse_any(text: str, fmt: str = "auto") -> _uuid.UUID:
    """把标准 UUID / 32 位 hex / Crockford Base32 解析为 uuid.UUID。"""
    if fmt not in ("auto", "hex", "b32", "uuid"):
        raise ValueError("unknown format: %r" % fmt)
    if fmt == "b32":
        return _from_crockford(text)
    compact = _to_compact(text)
    if len(compact) == 32 and all(c in _HEX_DIGITS for c in compact):
        return _uuid.UUID(compact)
    if fmt in ("hex", "uuid"):
        raise ValueError("not a valid 32-hex/UUID string: %r" % text)
    return _from_crockford(text)


def uuid_to_forms(u: _uuid.UUID) -> dict:
    return {"uuid": str(u), "hex": u.hex, "crockford": b32_encode(u.int, 26)}


def cmd_enc(args) -> int:
    try:
        u = parse_any(args.uuid, "uuid")
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    forms = uuid_to_forms(u)
    print("uuid:      %s" % forms["uuid"])
    print("hex:       %s" % forms["hex"])
    print("crockford: %s" % forms["crockford"])
    return 0


def cmd_dec(args) -> int:
    try:
        u = parse_any(args.compact, args.format)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    print(u)
    return 0


def cmd_selftest(_args) -> int:
    checks = []

    def check(name, cond):
        checks.append(bool(cond))
        print(("ok:   " if cond else "FAIL: ") + name)

    u = _uuid.UUID("3d813cbb-47fb-32ba-91df-831e1593ac29")
    forms = uuid_to_forms(u)
    check("hex form equals uuid.hex", forms["hex"] == "3d813cbb47fb32ba91df831e1593ac29")
    check("crockford length is 26", len(forms["crockford"]) == 26)
    check("crockford roundtrip", b32_decode(forms["crockford"]) == u.int)
    check("parse hex string", parse_any(forms["hex"]).int == u.int)
    check("parse canonical uuid", parse_any(str(u)).int == u.int)
    check("parse braced uuid", parse_any("{%s}" % u).int == u.int)
    check("parse urn:uuid:", parse_any("urn:uuid:%s" % u).int == u.int)

    # 已知向量：o/I/i/L 归一化为 0/1/1/1 -> 0b00001_00001_00001_00001 = 1057
    check("i/l/o normalization vector", b32_decode("oIiL") == (1 << 10) | (1 << 5) | 1)
    check("i/l/o encode vector", b32_encode(1057, 4) == "0111")
    noisy = forms["crockford"].lower().replace("0", "o").replace("1", "l")
    check("crockford tolerant decoding", parse_any(noisy, "b32").int == u.int)

    check("zero encodes to 26 zeros", b32_encode(0, 26) == "0" * 26)
    max_u = _uuid.UUID(int=(1 << 128) - 1)
    check("max uuid first char is 7", uuid_to_forms(max_u)["crockford"][0] == "7")
    check("max uuid roundtrip", parse_any(uuid_to_forms(max_u)["crockford"], "b32") == max_u)
    check("short b32 implies leading zeros", parse_any("0", "b32") == _uuid.UUID(int=0))

    def raises(fn):
        try:
            fn()
        except ValueError:
            return True
        return False

    check("letter U rejected", raises(lambda: b32_decode("0U00")))
    check("bad char rejected", raises(lambda: b32_decode("0@00")))
    check("27-char b32 rejected (>128 bits)", raises(lambda: parse_any("Z" * 27, "b32")))
    check("non-hex rejected as hex", raises(lambda: parse_any("xyz", "hex")))

    total = len(checks)
    if all(checks):
        print("selftest ok (%d/%d checks)" % (total, total))
        return 0
    print("selftest FAILED (%d/%d checks failed)" % (checks.count(False), total))
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="uuid-compact.py",
        description="UUID / 无连字符 hex / Crockford Base32 紧凑形式互相转换",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    pe = sub.add_parser("enc", help="UUID -> hex + Crockford Base32")
    pe.add_argument("uuid", help="标准 UUID（也接受 32 位 hex 写法）")
    pe.set_defaults(func=cmd_enc)
    pd = sub.add_parser("dec", help="紧凑形式 -> 标准 UUID")
    pd.add_argument("compact", help="hex / Crockford Base32 / 标准写法")
    pd.add_argument("--format", choices=["auto", "hex", "b32", "uuid"], default="auto",
                    help="强制指定输入格式（默认 auto 自动识别）")
    pd.set_defaults(func=cmd_dec)
    ps = sub.add_parser("selftest", help="运行内置自测")
    ps.set_defaults(func=cmd_selftest)
    return p


def main(argv=None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return args.func(args)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
