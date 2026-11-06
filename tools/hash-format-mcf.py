#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hash-format-mcf -- 将算法+盐+哈希打包成 Modular-Crypt-Format 风格字符串，并能解析还原参数。

格式: $<algo>$i=<iterations>$<salt_b64>$<digest_b64>
  algo       : pbkdf2-sha1 | pbkdf2-sha256 | pbkdf2-sha512
  iterations : PBKDF2 迭代次数（十进制，前缀 i=）
  salt/digest: 标准 base64（去填充，解析时自动补齐）

子命令:
  gen      由口令(+盐)派生 PBKDF2 摘要并输出 MCF 串（不带 --salt-hex 时用随机盐）
  encode   把已有的盐/摘要（十六进制）直接编码为 MCF 串
  parse    解析 MCF 串还原参数；--check-password 可验证口令（常数时间比较）
  selftest 内置自测（往返编解码、已知答案、非法输入拒绝）

示例:
  python hash-format-mcf.py gen --password 'S3cret!' --iterations 210000
  python hash-format-mcf.py gen --password pw --salt-hex 73616c74 --iterations 1000 --algo pbkdf2-sha512
  python hash-format-mcf.py parse '$pbkdf2-sha256$i=1000$c2FsdA$...' --check-password pw
  python hash-format-mcf.py encode --algo pbkdf2-sha256 --iterations 1000 --salt-hex 00112233 --digest-hex <64位hex>
  python hash-format-mcf.py selftest

仅用 Python 标准库；全部计算本地完成。
"""

import argparse
import base64
import getpass
import hashlib
import hmac
import secrets
import sys

ALGO2HASH = {
    "pbkdf2-sha1": "sha1",
    "pbkdf2-sha256": "sha256",
    "pbkdf2-sha512": "sha512",
}


def b64_encode_nopad(data: bytes) -> str:
    """标准 base64，去掉 '=' 填充。"""
    return base64.b64encode(data).decode("ascii").rstrip("=")


def b64_decode_nopad(text: str) -> bytes:
    """解码去填充 base64；自动补齐填充，校验字符集。"""
    if not text:
        raise ValueError("empty base64 field")
    pad = "=" * (-len(text) % 4)
    try:
        return base64.b64decode(text + pad, validate=True)
    except Exception as exc:
        raise ValueError(f"bad base64 field: {text!r}") from exc


def encode_mcf(algo: str, iterations: int, salt: bytes, digest: bytes) -> str:
    if algo not in ALGO2HASH:
        raise ValueError(f"unsupported algo: {algo!r} (known: {', '.join(sorted(ALGO2HASH))})")
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    if not salt:
        raise ValueError("salt must not be empty")
    if not digest:
        raise ValueError("digest must not be empty")
    return f"${algo}$i={iterations}${b64_encode_nopad(salt)}${b64_encode_nopad(digest)}"


def parse_mcf(mcf: str) -> dict:
    """解析 MCF 串，返回 algo/iterations/salt/digest；非法输入抛 ValueError。"""
    parts = mcf.split("$")
    if len(parts) != 5 or parts[0] != "":
        raise ValueError("expected format $<algo>$i=<n>$<salt>$<digest>")
    _, algo, iter_field, salt_s, digest_s = parts
    if algo not in ALGO2HASH:
        raise ValueError(f"unsupported algo: {algo!r}")
    if not iter_field.startswith("i=") or not iter_field[2:].isdigit():
        raise ValueError(f"bad iterations field: {iter_field!r}")
    iterations = int(iter_field[2:])
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    salt = b64_decode_nopad(salt_s)
    digest = b64_decode_nopad(digest_s)
    return {"algo": algo, "iterations": iterations, "salt": salt, "digest": digest}


def derive(algo: str, password: bytes, salt: bytes, iterations: int, dklen: int) -> bytes:
    return hashlib.pbkdf2_hmac(ALGO2HASH[algo], password, salt, iterations, dklen)


def cmd_gen(args):
    if args.password is not None:
        password = args.password.encode("utf-8")
    elif args.ask:
        password = getpass.getpass("password: ").encode("utf-8")
    else:
        raise ValueError("provide --password or --ask")
    if not password:
        raise ValueError("empty password")
    if args.salt_hex is not None:
        salt = bytes.fromhex(args.salt_hex)
    else:
        if not 1 <= args.salt_bytes <= 64:
            raise ValueError("--salt-bytes must be in 1..64")
        salt = secrets.token_bytes(args.salt_bytes)
    dklen = args.dklen or hashlib.new(ALGO2HASH[args.algo]).digest_size
    if not 1 <= dklen <= 512:
        raise ValueError("--dklen must be in 1..512")
    digest = derive(args.algo, password, salt, args.iterations, dklen)
    print(encode_mcf(args.algo, args.iterations, salt, digest))
    return 0


def cmd_encode(args):
    salt = bytes.fromhex(args.salt_hex)
    digest = bytes.fromhex(args.digest_hex)
    print(encode_mcf(args.algo, args.iterations, salt, digest))
    return 0


def cmd_parse(args):
    p = parse_mcf(args.mcf)
    print(f"algo        : {p['algo']}")
    print(f"iterations  : {p['iterations']}")
    print(f"salt(hex)   : {p['salt'].hex()}")
    print(f"digest(hex) : {p['digest'].hex()}")
    if args.check_password is not None:
        expect = derive(p["algo"], args.check_password.encode("utf-8"),
                        p["salt"], p["iterations"], len(p["digest"]))
        ok = hmac.compare_digest(expect, p["digest"])
        print(f"check       : {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    return 0


def cmd_selftest(_args):
    # 1) 标准库已知答案（PBKDF2-HMAC-SHA256, "password"/"salt", c=1, dkLen=32）
    v = hashlib.pbkdf2_hmac("sha256", b"password", b"salt", 1, 32)
    assert v.hex() == "120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b", v.hex()

    # 2) encode -> parse 往返一致
    salt = bytes(range(16))
    digest = derive("pbkdf2-sha256", b"pw", salt, 1000, 32)
    p = parse_mcf(encode_mcf("pbkdf2-sha256", 1000, salt, digest))
    assert p == {"algo": "pbkdf2-sha256", "iterations": 1000, "salt": salt, "digest": digest}, p

    # 3) 自定义 dklen 与另一算法同样可往返
    p2 = parse_mcf(encode_mcf("pbkdf2-sha512", 7, b"s", b"\xff" * 64))
    assert p2["digest"] == b"\xff" * 64 and p2["iterations"] == 7 and p2["algo"] == "pbkdf2-sha512"

    # 4) 非法输入必须被拒绝
    for bad in ["", "abc", "$pbkdf2-sha256$x=1$AA$AA", "$md5$i=1$AA$AA",
                "$pbkdf2-sha256$i=0$AA$AA", "$pbkdf2-sha256$i=1$A$AA",
                "$pbkdf2-sha256$i=1$!!$AA", "$pbkdf2-sha256$i=1$AA$"]:
        try:
            parse_mcf(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"should reject: {bad!r}")

    # 5) 错误口令校验必然失败
    m = encode_mcf("pbkdf2-sha256", 10, b"salt", derive("pbkdf2-sha256", b"right", b"salt", 10, 32))
    q = parse_mcf(m)
    wrong = derive("pbkdf2-sha256", b"wrong", q["salt"], q["iterations"], len(q["digest"]))
    assert not hmac.compare_digest(wrong, q["digest"])

    print("selftest: 5/5 checks passed")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="hash-format-mcf",
                                 description="PBKDF2 Modular-Crypt-Format encoder/parser (stdlib only)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen", help="generate MCF string from a password")
    g.add_argument("--password", help="password on argv (use --ask to avoid shell history)")
    g.add_argument("--ask", action="store_true", help="prompt for password without echo")
    g.add_argument("--algo", choices=sorted(ALGO2HASH), default="pbkdf2-sha256")
    g.add_argument("--iterations", type=int, default=210000)
    g.add_argument("--salt-hex", help="explicit salt in hex (random salt otherwise)")
    g.add_argument("--salt-bytes", type=int, default=16, help="random salt length in bytes (default 16)")
    g.add_argument("--dklen", type=int, help="digest length in bytes (default: hash size)")
    g.set_defaults(func=cmd_gen)

    e = sub.add_parser("encode", help="encode existing salt/digest (hex) into MCF string")
    e.add_argument("--algo", choices=sorted(ALGO2HASH), default="pbkdf2-sha256")
    e.add_argument("--iterations", type=int, required=True)
    e.add_argument("--salt-hex", required=True)
    e.add_argument("--digest-hex", required=True)
    e.set_defaults(func=cmd_encode)

    p = sub.add_parser("parse", help="parse MCF string back into parameters")
    p.add_argument("mcf")
    p.add_argument("--check-password", help="verify this password against the digest")
    p.set_defaults(func=cmd_parse)

    t = sub.add_parser("selftest", help="run built-in self test")
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
