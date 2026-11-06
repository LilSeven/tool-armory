#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HOTP 计数器口令生成器 (RFC 4226)。

基于共享密钥与递增计数器生成 HMAC 一次性口令，支持批量列出一段计数器区间的口令
（例如打印一串应急恢复码）。仅供本人账号、授权测试或教学演示使用。

用法 (Windows Git Bash):
  python -I hotp-gen.py --secret GEZDGNBVGY3TQOJQ --counter 0             # 生成单个
  python -I hotp-gen.py --secret GEZDGNBVGY3TQOJQ --counter 0 --count 5   # 批量列出 counter 0..4
  python -I hotp-gen.py --secret 3132333435363738393031323334353637383930 --hex --counter 9
  python -I hotp-gen.py --secret GEZDGNBVGY3TQOJQ --counter 0 --quiet     # 只输出口令，每行一个
  python -I hotp-gen.py --selftest                                        # RFC 4226 官方向量自测

退出码: 0 = 成功/自测通过; 2 = 参数或密钥错误。
"""

import argparse
import base64
import binascii
import hashlib
import hmac
import re
import struct
import sys

ALGOS = {"SHA1": hashlib.sha1, "SHA256": hashlib.sha256, "SHA512": hashlib.sha512}

# RFC 4226 Appendix D 测试向量 (6 位, HMAC-SHA1, 密钥为 ASCII "12345678901234567890")
RFC4226_VECTORS = (
    "755224", "287082", "359152", "969429", "338314",
    "254676", "287922", "162583", "399871", "520489",
)


def hotp(key, counter, digits=6, algo="SHA1"):
    """RFC 4226 HOTP: HMAC-<algo>(key, 8 字节大端计数器) + 动态截断。"""
    digest = hmac.new(key, struct.pack(">Q", counter), ALGOS[algo]).digest()
    offset = digest[-1] & 0x0F
    code = ((digest[offset] & 0x7F) << 24
            | digest[offset + 1] << 16
            | digest[offset + 2] << 8
            | digest[offset + 3]) % (10 ** digits)
    return str(code).zfill(digits)


def parse_secret(text, hex_mode=False):
    """解析密钥: 默认 base32 (Google Authenticator 格式，忽略空格/连字符/大小写)；--hex 时按十六进制。"""
    if hex_mode:
        return bytes.fromhex(re.sub(r"[\s:-]+", "", text))
    compact = re.sub(r"[\s-]+", "", text).upper().rstrip("=")
    if not compact:
        raise ValueError("密钥为空")
    if not re.fullmatch(r"[A-Z2-7]+", compact):
        raise ValueError("不是合法的 base32 字符集 (应仅含 A-Z2-7，可用 --hex 改按十六进制)")
    return base64.b32decode(compact + "=" * ((8 - len(compact) % 8) % 8), casefold=True)


def selftest():
    key = bytes.fromhex("3132333435363738393031323334353637383930")  # ASCII "12345678901234567890"
    failures = 0
    for i, expect in enumerate(RFC4226_VECTORS):
        got = hotp(key, i, 6, "SHA1")
        ok = got == expect
        print("[%s] counter=%d got=%s expect=%s" % ("PASS" if ok else "FAIL", i, got, expect))
        failures += 0 if ok else 1
    if failures:
        print("SELFTEST FAILED: %d 项不匹配" % failures, file=sys.stderr)
        return 1
    print("SELFTEST OK: RFC 4226 全部 %d 个向量通过" % len(RFC4226_VECTORS))
    return 0


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="HOTP 计数器口令生成器 (RFC 4226)")
    ap.add_argument("--secret", help="base32 密钥 (忽略空格/连字符/大小写); 配合 --hex 可按十六进制")
    ap.add_argument("--hex", dest="hex_mode", action="store_true", help="把 --secret 按十六进制解析")
    ap.add_argument("--counter", type=int, default=0, help="起始计数器值 (默认 0)")
    ap.add_argument("--count", type=int, default=1, help="批量生成的口令个数 (默认 1)")
    ap.add_argument("--digits", type=int, choices=(6, 8), default=6, help="口令位数 (默认 6)")
    ap.add_argument("--algorithm", default="SHA1", help="HMAC 算法 SHA1/SHA256/SHA512 (默认 SHA1)")
    ap.add_argument("--quiet", action="store_true", help="只输出口令本身，每行一个")
    ap.add_argument("--selftest", action="store_true", help="运行 RFC 4226 官方向量自测")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.secret:
        ap.error("需要 --secret 提供密钥 (或使用 --selftest)")
    if args.counter < 0:
        print("counter 不能为负数", file=sys.stderr)
        return 2
    if args.count < 1 or args.count > 1000:
        print("count 取值应在 1-1000 之间", file=sys.stderr)
        return 2
    algo = args.algorithm.upper()
    if algo not in ALGOS:
        print("不支持的算法: %s (可选 SHA1/SHA256/SHA512)" % algo, file=sys.stderr)
        return 2

    try:
        key = parse_secret(args.secret, args.hex_mode)
    except (ValueError, binascii.Error) as exc:
        print("密钥解析失败: %s" % exc, file=sys.stderr)
        return 2

    for c in range(args.counter, args.counter + args.count):
        code = hotp(key, c, args.digits, algo)
        if args.quiet:
            print(code)
        else:
            print("counter %-6d -> %s" % (c, code))
    return 0


if __name__ == "__main__":
    sys.exit(main())
