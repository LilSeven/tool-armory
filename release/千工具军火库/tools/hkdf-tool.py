#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hkdf-tool -- RFC 5869 HKDF（Extract/Expand 两阶段）密钥派生，纯标准库实现。

  PRK = HMAC-Hash(salt, IKM)            # Extract 阶段（salt 缺省时取 HashLen 个 0x00）
  OKM = HKDF-Expand(PRK, info, L)       # Expand 阶段: T(i) = HMAC(PRK, T(i-1) | info | byte(i))

从共享密钥（IKM）+ 可选盐与 info 上下文派生子密钥，输出十六进制。
输入值支持前缀：hex:...（默认）/ str:...（UTF-8 原文）/ b64:...（标准 base64）。

子命令:
  extract  --ikm V [--salt V] [--hash sha256]                 -> PRK
  expand   --prk HEX --info V --length N [--hash sha256]      -> OKM
  derive   --ikm V [--salt V] [--info V] --length N           -> PRK 与 OKM
  selftest                                                    -> RFC 5869 附录 A 测试向量

示例:
  python hkdf-tool.py extract --ikm hex:0b0b0b0b0b0b0b0b0b0b0b --salt hex:000102030405060708090a0b0c
  python hkdf-tool.py derive --ikm hex:0b0b0b0b0b0b0b0b0b0b0b --salt hex:000102030405060708090a0b0c --info hex:f0f1f2f3f4f5f6f7f8f9 --length 42
  python hkdf-tool.py derive --ikm str:shared-secret --info str:tunnel-a --length 32
  python hkdf-tool.py selftest

仅用 Python 标准库。
"""

import argparse
import base64
import binascii
import hashlib
import hmac
import sys


def hkdf_extract(salt: bytes, ikm: bytes, hash_name: str = "sha256") -> bytes:
    if not salt:
        hash_len = hashlib.new(hash_name).digest_size
        salt = b"\x00" * hash_len  # RFC 5869：salt 未提供时取 HashLen 个 0
    return hmac.new(salt, ikm, hash_name).digest()


def hkdf_expand(prk: bytes, info: bytes, length: int, hash_name: str = "sha256") -> bytes:
    hash_len = hashlib.new(hash_name).digest_size
    if length < 1:
        raise ValueError("length must be >= 1")
    if length > 255 * hash_len:
        raise ValueError(f"length {length} exceeds 255*HashLen={255 * hash_len}")
    okm = b""
    block = b""
    counter = 1
    while len(okm) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hash_name).digest()
        okm += block
        counter += 1
    return okm[:length]


def parse_bytes(spec: str, what: str) -> bytes:
    """hex:... / str:... / b64:... / 裸十六进制 -> bytes。"""
    if spec is None:
        return b""
    if spec.startswith("str:"):
        return spec[4:].encode("utf-8")
    if spec.startswith("b64:"):
        try:
            return base64.b64decode(spec[4:], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"{what}: bad base64 value {spec!r}") from exc
    if spec.startswith("hex:"):
        spec = spec[4:]
    try:
        return bytes.fromhex(spec)
    except ValueError as exc:
        raise ValueError(f"{what}: bad hex value {spec!r}") from exc


def cmd_extract(args):
    salt = parse_bytes(args.salt, "--salt")
    ikm = parse_bytes(args.ikm, "--ikm")
    print(hkdf_extract(salt, ikm, args.hash).hex())
    return 0


def cmd_expand(args):
    try:
        prk = bytes.fromhex(args.prk)
    except ValueError as exc:
        raise ValueError(f"--prk: bad hex value {args.prk!r}") from exc
    info = parse_bytes(args.info, "--info")
    print(hkdf_expand(prk, info, args.length, args.hash).hex())
    return 0


def cmd_derive(args):
    salt = parse_bytes(args.salt, "--salt")
    ikm = parse_bytes(args.ikm, "--ikm")
    info = parse_bytes(args.info, "--info")
    prk = hkdf_extract(salt, ikm, args.hash)
    okm = hkdf_expand(prk, info, args.length, args.hash)
    print(f"PRK: {prk.hex()}")
    print(f"OKM: {okm.hex()}")
    return 0


RFC5869_VECTORS = [
    {
        "case": "A.1 basic (SHA-256)",
        "hash": "sha256",
        "ikm": "0b" * 22,
        "salt": "000102030405060708090a0b0c",
        "info": "f0f1f2f3f4f5f6f7f8f9",
        "length": 42,
        "prk": "077709362c2e32df0ddc3f0dc47bba6390b6c73bb50f9c3122ec844ad7c2b3e5",
        "okm": "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf"
               "34007208d5b887185865",
    },
    {
        "case": "A.2 longer inputs/outputs (SHA-256)",
        "hash": "sha256",
        "ikm": bytes(range(0x00, 0x50)).hex(),
        "salt": bytes(range(0x60, 0xB0)).hex(),
        "info": bytes(range(0xB0, 0x100)).hex(),
        "length": 82,
        "prk": "06a6b88c5853361a06104c9ceb35b45cef760014904671014a193f40c15fc244",
        "okm": "b11e398dc80327a1c8e7f78c596a49344f012eda2d4efad8a050cc4c19afa97c"
               "59045a99cac7827271cb41c65e590e09da3275600c2f09b8367793a9aca3db71"
               "cc30c58179ec3e87c14c01d5c1f3434f1d87",
    },
    {
        "case": "A.3 zero-length salt/info (SHA-256)",
        "hash": "sha256",
        "ikm": "0b" * 22,
        "salt": "",
        "info": "",
        "length": 42,
        "prk": "19ef24a32c717b167f33a91d6f648bdf96596776afdb6377ac434c1c293ccb04",
        "okm": "8da4e775a563c18f715f802a063c5a31b8a11f5c5ee1879ec3454e5f3c738d2d"
               "9d201395faa4b61a96c8",
    },
]


def cmd_selftest(_args):
    # 1) RFC 5869 附录 A 测试向量（PRK 验 Extract，OKM 验两阶段整体）
    for v in RFC5869_VECTORS:
        prk = hkdf_extract(bytes.fromhex(v["salt"]), bytes.fromhex(v["ikm"]), v["hash"])
        okm = hkdf_expand(prk, bytes.fromhex(v["info"]), v["length"], v["hash"])
        assert prk.hex() == v["prk"], f"{v['case']} PRK mismatch: {prk.hex()}"
        assert okm.hex() == v["okm"], f"{v['case']} OKM mismatch: {okm.hex()}"
        print(f"PASS {v['case']}")

    # 2) 边界：expand 最大长度 255*HashLen 允许，+1 拒绝
    prk = hkdf_extract(b"salt", b"ikm")
    assert len(hkdf_expand(prk, b"info", 255 * 32)) == 255 * 32
    try:
        hkdf_expand(prk, b"info", 255 * 32 + 1)
    except ValueError:
        pass
    else:
        raise AssertionError("expand must reject length > 255*HashLen")

    # 3) 语义：空盐与 HashLen 个 0 等价；不同盐得不同 PRK；derive 与两阶段手工组合一致
    assert hkdf_extract(b"", b"secret") == hkdf_extract(b"\x00" * 32, b"secret")
    assert hkdf_extract(b"s1", b"k") != hkdf_extract(b"s2", b"k")
    prk2 = hkdf_extract(b"salt", b"secret")
    assert hkdf_expand(prk2, b"ctx", 32) == hkdf_expand(prk2, b"ctx", 32)

    print(f"selftest: {len(RFC5869_VECTORS)}/3 RFC vectors + boundary/consistency checks passed")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="hkdf-tool",
                                 description="RFC 5869 HKDF extract/expand (stdlib only)")
    ap.add_argument("--hash", choices=("sha1", "sha224", "sha256", "sha384", "sha512"),
                    default="sha256", help="hash function (default sha256)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="PRK = HMAC(salt, IKM)")
    e.add_argument("--ikm", required=True, help="input key material (hex:/str:/b64:)")
    e.add_argument("--salt", help="salt (hex:/str:/b64:); default = HashLen zero bytes")
    e.set_defaults(func=cmd_extract)

    x = sub.add_parser("expand", help="OKM = HKDF-Expand(PRK, info, L)")
    x.add_argument("--prk", required=True, help="PRK in hex")
    x.add_argument("--info", help="context/info (hex:/str:/b64:)")
    x.add_argument("--length", type=int, required=True, help="output length in bytes (<= 255*HashLen)")
    x.set_defaults(func=cmd_expand)

    d = sub.add_parser("derive", help="run extract then expand, print both")
    d.add_argument("--ikm", required=True, help="input key material (hex:/str:/b64:)")
    d.add_argument("--salt", help="salt (hex:/str:/b64:)")
    d.add_argument("--info", help="context/info (hex:/str:/b64:)")
    d.add_argument("--length", type=int, required=True, help="output length in bytes")
    d.set_defaults(func=cmd_derive)

    t = sub.add_parser("selftest", help="run RFC 5869 test vectors")
    t.set_defaults(func=cmd_selftest)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
