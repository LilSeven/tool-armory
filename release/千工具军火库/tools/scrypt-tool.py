#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scrypt-tool.py —— 用 hashlib.scrypt 生成/校验口令哈希，N/r/p 参数可调。

存储格式（单行）:
  scrypt$<N>$<r>$<p>$<salt_base64>$<hash_base64>

内存开销约为 128*N*r*p 字节（默认 N=16384, r=8, p=1 约 16 MiB）；
参数合计内存超过 1 GiB 时需显式加 --allow-huge。

用法:
  python -I scrypt-tool.py hash --password 'S3cret!' [-N 16384] [-r 8] [-p 1] [--dklen 64] [--salt-len 16]
  python -I scrypt-tool.py verify --password 'S3cret!' --hash 'scrypt$16384$8$1$<salt_b64>$<hash_b64>'
  python -I scrypt-tool.py verify --password 'S3cret!' --hash-file stored.txt

示例（小参数快速验证）:
  H=$(python -I scrypt-tool.py hash --password demo -N 1024)
  python -I scrypt-tool.py verify --password demo --hash "$H"

退出码: hash 成功 0；verify 匹配 0 / 不匹配 1；参数或环境错误 2。
依赖: hashlib.scrypt（需 OpenSSL 1.1+ 支持），其余仅标准库。
"""

import argparse
import base64
import getpass
import hashlib
import hmac
import secrets
import sys

MAX_MEM_DEFAULT = 1 << 30  # 1 GiB 上限，超过需 --allow-huge


def _reconfigure_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def read_password(args):
    if args.password is not None:
        return args.password
    try:
        if not sys.stdin.isatty():
            return sys.stdin.readline().rstrip("\r\n")
    except (AttributeError, ValueError, OSError):
        pass
    return getpass.getpass("Password: ")


def validate_params(n, r, p, allow_huge):
    if n < 2 or (n & (n - 1)) != 0:
        raise ValueError("N 必须 >= 2 且为 2 的幂")
    if r < 1 or p < 1:
        raise ValueError("r 与 p 必须 >= 1")
    needed = 128 * n * r * p
    if needed > MAX_MEM_DEFAULT and not allow_huge:
        raise ValueError("参数需约 %.1f MiB 内存（超过 1 GiB 上限），确认安全请加 --allow-huge"
                         % (needed / 1048576))
    return needed


def derive(password, salt, n, r, p, dklen):
    needed = 128 * n * r * p
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                          dklen=dklen, maxmem=needed + (16 << 20))


def main(argv=None):
    _reconfigure_stdio()
    if not hasattr(hashlib, "scrypt"):
        sys.stderr.write("错误: 当前 Python 的 hashlib 没有 scrypt（需要 OpenSSL 1.1+ 支持）\n")
        return 2

    ap = argparse.ArgumentParser(
        prog="scrypt-tool.py",
        description="用 hashlib.scrypt 生成/校验口令哈希（scrypt$N$r$p$salt$hash 格式）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_hash = sub.add_parser("hash", help="生成口令哈希")
    p_hash.add_argument("--password", help="明文口令（不推荐；缺省走 stdin 或 getpass）")
    p_hash.add_argument("-N", type=int, default=16384,
                        help="CPU/内存成本参数（默认 16384，须为 2 的幂）")
    p_hash.add_argument("-r", type=int, default=8, help="块大小（默认 8）")
    p_hash.add_argument("-p", type=int, default=1, help="并行度（默认 1）")
    p_hash.add_argument("--dklen", type=int, default=64, help="派生长度（字节，默认 64）")
    p_hash.add_argument("--salt-len", type=int, default=16, help="随机盐长度（字节，默认 16）")
    p_hash.add_argument("--allow-huge", action="store_true",
                        help="允许超过 1 GiB 的内存参数")

    p_verify = sub.add_parser("verify", help="校验口令哈希")
    p_verify.add_argument("--password", help="明文口令（不推荐；缺省走 stdin 或 getpass）")
    p_verify.add_argument("--hash", help="scrypt-tool hash 输出的存储串")
    p_verify.add_argument("--hash-file", help="从文件首行读取存储串")
    p_verify.add_argument("--allow-huge", action="store_true")

    args = ap.parse_args(argv)

    try:
        if args.cmd == "hash":
            if args.dklen < 1 or args.salt_len < 1:
                raise ValueError("--dklen/--salt-len 必须 >= 1")
            validate_params(args.N, args.r, args.p, args.allow_huge)
            password = read_password(args)
            if not password:
                raise ValueError("口令为空：请用 --password、管道 stdin 或交互输入提供")
            salt = secrets.token_bytes(args.salt_len)
            derived = derive(password, salt, args.N, args.r, args.p, args.dklen)
            print("scrypt$%d$%d$%d$%s$%s" % (
                args.N, args.r, args.p,
                base64.b64encode(salt).decode("ascii"),
                base64.b64encode(derived).decode("ascii")))
            return 0

        # verify
        encoded = None
        if args.hash:
            encoded = args.hash.strip()
        elif args.hash_file:
            with open(args.hash_file, "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        encoded = line.strip()
                        break
            if not encoded:
                raise ValueError("哈希文件为空: %s" % args.hash_file)
        if not encoded:
            raise ValueError("必须提供 --hash 或 --hash-file")
        parts = encoded.split("$")
        if len(parts) != 6 or parts[0] != "scrypt":
            raise ValueError("格式应为 scrypt$<N>$<r>$<p>$<salt_b64>$<hash_b64>")
        try:
            n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        except ValueError:
            raise ValueError("N/r/p 必须是整数")
        validate_params(n, r, p, args.allow_huge)
        salt = base64.b64decode(parts[4], validate=True)
        stored = base64.b64decode(parts[5], validate=True)
        if not salt or not stored:
            raise ValueError("盐或哈希为空")
        password = read_password(args)
        if not password:
            raise ValueError("口令为空：请用 --password、管道 stdin 或交互输入提供")
        derived = derive(password, salt, n, r, p, dklen=len(stored))
        if hmac.compare_digest(derived, stored):
            print("MATCH —— 口令与存储哈希一致")
            return 0
        print("MISMATCH —— 口令不匹配")
        return 1
    except (ValueError, OSError) as exc:
        sys.stderr.write("错误: %s\n" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
