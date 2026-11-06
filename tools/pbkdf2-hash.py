#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pbkdf2-hash.py —— 生成 PBKDF2-HMAC-SHA256 口令哈希，迭代次数与盐长度可调。

输出存储格式（单行，可直接交给 pbkdf2-verify.py 校验）:
  pbkdf2_sha256$<iterations>$<salt_base64>$<hash_base64>

用法:
  python -I pbkdf2-hash.py --password 'S3cret!' [-i 600000] [-s 16] [-l 32]
  python -I pbkdf2-hash.py                    # 交互式隐藏输入（getpass）
  printf 'S3cret!\n' | python -I pbkdf2-hash.py -i 1000   # 从 stdin 第一行读口令

安全提示:
  * --password 会留在 shell 历史与进程列表中，敏感口令请优先用交互或 stdin 方式。
  * OWASP（2023）建议 PBKDF2-HMAC-SHA256 迭代次数不低于 600000，盐长度不低于 16 字节。
退出码: 0 成功；2 参数错误。仅使用 Python 标准库。
"""

import argparse
import base64
import getpass
import hashlib
import secrets
import sys


def _reconfigure_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def read_password(args):
    """取口令: --password 优先；否则非 tty 的 stdin 第一行；否则 getpass 隐藏输入。"""
    if args.password is not None:
        return args.password
    try:
        if not sys.stdin.isatty():
            return sys.stdin.readline().rstrip("\r\n")
    except (AttributeError, ValueError, OSError):
        pass
    return getpass.getpass("Password: ")


def main(argv=None):
    _reconfigure_stdio()
    ap = argparse.ArgumentParser(
        prog="pbkdf2-hash.py",
        description="生成 PBKDF2-HMAC-SHA256 口令哈希（pbkdf2_sha256$iter$salt$hash 格式）")
    ap.add_argument("--password", help="明文口令（不推荐，见 docstring 安全提示）")
    ap.add_argument("-i", "--iterations", type=int, default=600000,
                    help="迭代次数（默认 600000）")
    ap.add_argument("-s", "--salt-len", type=int, default=16,
                    help="随机盐长度（字节，默认 16）")
    ap.add_argument("-l", "--dklen", type=int, default=32,
                    help="派生密钥长度（字节，默认 32）")
    args = ap.parse_args(argv)

    if args.iterations < 1:
        ap.error("--iterations 必须 >= 1")
    if args.salt_len < 1:
        ap.error("--salt-len 必须 >= 1")
    if args.dklen < 1:
        ap.error("--dklen 必须 >= 1")

    password = read_password(args)
    if not password:
        ap.error("口令为空：请用 --password、管道 stdin 或交互输入提供")

    salt = secrets.token_bytes(args.salt_len)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, args.iterations, dklen=args.dklen)
    print("pbkdf2_sha256$%d$%s$%s" % (
        args.iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derived).decode("ascii")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
