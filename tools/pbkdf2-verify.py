#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pbkdf2-verify.py —— 校验明文口令是否匹配 pbkdf2-hash.py 生成的存储哈希。

重算 PBKDF2-HMAC-SHA256 后用 hmac.compare_digest 做常数时间比较，避免计时侧信道泄露。

用法:
  python -I pbkdf2-verify.py --hash 'pbkdf2_sha256$600000$<salt_b64>$<hash_b64>' --password 'S3cret!'
  printf 'S3cret!\n' | python -I pbkdf2-verify.py --hash-file stored.txt
  python -I pbkdf2-verify.py --hash "$(python -I pbkdf2-hash.py -i 1000 --password demo)" --password demo

退出码: 0 匹配；1 不匹配；2 用法/解析错误。仅使用 Python 标准库。
"""

import argparse
import base64
import getpass
import hashlib
import hmac
import sys


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


def load_encoded(args):
    if args.hash:
        return args.hash.strip()
    if args.hash_file:
        with open(args.hash_file, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    return line
        raise ValueError("哈希文件为空: %s" % args.hash_file)
    return None


def parse_encoded(encoded):
    parts = encoded.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        raise ValueError("格式应为 pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>")
    try:
        iterations = int(parts[1])
    except ValueError:
        raise ValueError("迭代次数不是整数: %r" % parts[1])
    if iterations < 1:
        raise ValueError("迭代次数必须 >= 1")
    salt = base64.b64decode(parts[2], validate=True)
    stored = base64.b64decode(parts[3], validate=True)
    if not salt or not stored:
        raise ValueError("盐或哈希为空")
    return iterations, salt, stored


def main(argv=None):
    _reconfigure_stdio()
    ap = argparse.ArgumentParser(
        prog="pbkdf2-verify.py",
        description="校验口令是否匹配 PBKDF2-HMAC-SHA256 存储哈希（常数时间比较）")
    ap.add_argument("--hash", help="pbkdf2-hash.py 输出的存储串")
    ap.add_argument("--hash-file", help="从文件首行读取存储串")
    ap.add_argument("--password", help="明文口令（不推荐；缺省走 stdin 或 getpass）")
    args = ap.parse_args(argv)

    try:
        encoded = load_encoded(args)
        if not encoded:
            ap.error("必须提供 --hash 或 --hash-file")
        iterations, salt, stored = parse_encoded(encoded)
    except (ValueError, OSError) as exc:
        ap.error("解析存储哈希失败: %s" % exc)

    password = read_password(args)
    if not password:
        ap.error("口令为空：请用 --password、管道 stdin 或交互输入提供")

    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations, dklen=len(stored))
    if hmac.compare_digest(derived, stored):
        print("MATCH —— 口令与存储哈希一致")
        return 0
    print("MISMATCH —— 口令不匹配")
    return 1


if __name__ == "__main__":
    sys.exit(main())
