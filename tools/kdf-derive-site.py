#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kdf-derive-site -- 站点密码派生器：由主口令+站点名派生各站点独立密码（本地计算，不出网）。

原理：以主口令为输入密钥材料、规范化站点名为盐/上下文，
用 PBKDF2-HMAC-SHA256（默认，带工作因子）或 HKDF-SHA256（RFC 5869）
派生字节流，再以“拒绝采样”无偏映射到选定字母表，得到该站点专用密码。
同一主口令在不同站点派生出互不相关的强口令，只需记住主口令。

示例:
  python kdf-derive-site.py derive --site github.com                # 交互输入主口令（不回显）
  python kdf-derive-site.py derive --master 'correct horse' --site github.com --length 24
  python kdf-derive-site.py derive --master '...' --site github.com --kdf hkdf --preset full
  echo 'master' | python kdf-derive-site.py derive --site github.com --master-stdin
  python kdf-derive-site.py selftest

仅用 Python 标准库；无任何网络访问。注意 --master 会留在 shell 历史，
交互场景建议用 --ask 或 --master-stdin。
"""

import argparse
import getpass
import hashlib
import hmac
import sys

PRESETS = {
    "alnum": "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    "full": "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            "!@#$%^&*()-_=+[]{};:,.<>?",
    "lower": "abcdefghijklmnopqrstuvwxyz",
    "digits": "0123456789",
}


def hkdf_extract(salt: bytes, ikm: bytes, hash_name: str = "sha256") -> bytes:
    """RFC 5869 Extract: PRK = HMAC-Hash(salt, IKM)。"""
    return hmac.new(salt, ikm, hash_name).digest()


def hkdf_expand(prk: bytes, info: bytes, length: int, hash_name: str = "sha256") -> bytes:
    """RFC 5869 Expand: T(i) = HMAC(PRK, T(i-1) | info | i)。"""
    hsize = hashlib.new(hash_name).digest_size
    if length > 255 * hsize:
        raise ValueError("length too large for HKDF-Expand")
    okm = b""
    block = b""
    i = 1
    while len(okm) < length:
        block = hmac.new(prk, block + info + bytes([i]), hash_name).digest()
        okm += block
        i += 1
    return okm[:length]


def keystream_to_password(okm: bytes, alphabet: str, length: int) -> str:
    """拒绝采样把字节流无偏映射到字母表（消除取模偏差）。"""
    n = len(alphabet)
    limit = 256 - (256 % n)
    out = []
    for b in okm:
        if b < limit:
            out.append(alphabet[b % n])
            if len(out) == length:
                return "".join(out)
    raise RuntimeError("not enough derived bytes (internal margin too small)")


def derive_site_password(master: bytes, site: str, kdf: str = "pbkdf2",
                         iterations: int = 200000, length: int = 20,
                         alphabet: str = PRESETS["alnum"]) -> str:
    if not master:
        raise ValueError("empty master password")
    site_norm = site.strip().lower()
    if not site_norm:
        raise ValueError("empty site name")
    if not 8 <= length <= 256:
        raise ValueError("--length must be in 8..256")
    info = b"kdf-derive-site/v1|pw|" + site_norm.encode("utf-8")
    if kdf == "pbkdf2":
        if iterations < 1:
            raise ValueError("--iterations must be >= 1")
        salt = b"kdf-derive-site/v1|salt|" + site_norm.encode("utf-8")
        prk = hashlib.pbkdf2_hmac("sha256", master, salt, iterations, 32)
    elif kdf == "hkdf":
        prk = hkdf_extract(site_norm.encode("utf-8"), master)
    else:
        raise ValueError(f"unknown kdf: {kdf!r} (pbkdf2 | hkdf)")
    okm = hkdf_expand(prk, info, length * 2 + 8)
    return keystream_to_password(okm, alphabet, length)


def cmd_derive(args):
    if args.master is not None:
        master = args.master.encode("utf-8")
    elif args.master_stdin:
        master = sys.stdin.buffer.readline().rstrip(b"\r\n")
    else:
        master = getpass.getpass("master password: ").encode("utf-8")
    pw = derive_site_password(master, args.site, args.kdf, args.iterations,
                              args.length, PRESETS[args.preset])
    print(pw)
    return 0


def cmd_selftest(_args):
    master = b"correct horse battery staple"

    # 1) 确定性：同输入同输出
    a = derive_site_password(master, "github.com", "pbkdf2", 1000, 20)
    assert a == derive_site_password(master, "github.com", "pbkdf2", 1000, 20)

    # 2) 站点名归一化（大小写/首尾空白不影响结果）
    assert a == derive_site_password(master, "  GitHub.COM ", "pbkdf2", 1000, 20)

    # 3) 不同站点、不同主口令派生结果互不相同
    assert a != derive_site_password(master, "gitlab.com", "pbkdf2", 1000, 20)
    assert a != derive_site_password(b"another master", "github.com", "pbkdf2", 1000, 20)

    # 4) 长度与字母表约束
    assert len(a) == 20 and all(ch in PRESETS["alnum"] for ch in a)
    e = derive_site_password(master, "github.com", "hkdf", 0, 24, PRESETS["full"])
    assert len(e) == 24 and all(ch in PRESETS["full"] for ch in e)
    f = derive_site_password(master, "github.com", "pbkdf2", 1000, 64)
    assert len(f) == 64 and len(set(f)) > 30  # 64 位下应有多样性

    # 5) hkdf 与 pbkdf2 两条路径都确定且互不相同
    h = derive_site_password(master, "github.com", "hkdf", 0, 20)
    assert h == derive_site_password(master, "github.com", "hkdf", 0, 20) and h != a

    print("selftest: determinism / site isolation / alphabet / policy checks passed")
    print("sample (pbkdf2, test master, not for real use):", a)
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="kdf-derive-site",
                                 description="derive per-site passwords from a master password (local only)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("derive", help="derive the password for one site")
    d.add_argument("--site", required=True, help="site name, e.g. github.com")
    d.add_argument("--master", help="master password on argv (use --ask/--master-stdin to avoid history)")
    d.add_argument("--master-stdin", action="store_true", help="read master password from first stdin line")
    d.add_argument("--kdf", choices=sorted(("pbkdf2", "hkdf")), default="pbkdf2")
    d.add_argument("--iterations", type=int, default=200000, help="PBKDF2 iterations (default 200000)")
    d.add_argument("--length", type=int, default=20, help="password length (8..256)")
    d.add_argument("--preset", choices=sorted(PRESETS), default="alnum",
                   help="alphabet preset (default alnum)")
    d.set_defaults(func=cmd_derive)

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
