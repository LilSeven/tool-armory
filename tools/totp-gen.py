#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TOTP 动态码生成器 (RFC 6238)。

基于共享密钥与当前时间生成 6/8 位时间一次性口令，兼容 Google Authenticator
导出的 base32 密钥与 otpauth:// URI。仅供本人账号、授权测试或教学演示使用，
请勿用于绕过他人账号的安全机制。

用法 (Windows Git Bash):
  python -I totp-gen.py --secret JBSWY3DPEHPK3PXP                     # 默认 SHA1/6位/30s
  python -I totp-gen.py --secret JBSWY3DPEHPK3PXP --digits 8 --period 60 --algorithm SHA256
  python -I totp-gen.py --secret "jbsw y3dp ehpk 3pxp" --quiet        # 忽略空格/大小写，只输出验证码
  python -I totp-gen.py --uri "otpauth://totp/ACME:alice?secret=JBSWY3DPEHPK3PXP&digits=6&period=30&issuer=ACME"
  python -I totp-gen.py --secret GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ --time 59 --digits 8   # RFC6238 向量
  python -I totp-gen.py --selftest                                    # 运行 RFC6238 官方向量自测

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
import time
import urllib.parse

ALGOS = {"SHA1": hashlib.sha1, "SHA256": hashlib.sha256, "SHA512": hashlib.sha512}

# RFC 6238 Appendix B 测试向量 (8 位, T0=0, X=30)
RFC6238_VECTORS = (
    (59, "94287082", "46119246", "90693936"),
    (1111111109, "07081804", "68084774", "25091201"),
    (1111111111, "14050471", "67062674", "99943326"),
    (1234567890, "89005924", "91819424", "93441116"),
    (2000000000, "69279037", "90698825", "38618901"),
    (20000000000, "65353130", "77737706", "47863826"),
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


def totp(key, when, period=30, digits=6, algo="SHA1"):
    """RFC 6238 TOTP: counter = floor(unix_time / period)。"""
    return hotp(key, int(when // period), digits, algo)


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


def parse_otpauth(uri):
    """解析 otpauth://totp/... URI，返回 (标签, {secret, digits, period, algorithm})。"""
    p = urllib.parse.urlparse(uri)
    if p.scheme != "otpauth" or p.netloc.lower() != "totp":
        raise ValueError("不是 otpauth://totp/ URI")
    q = urllib.parse.parse_qs(p.query)
    if "secret" not in q:
        raise ValueError("URI 缺少 secret 参数")
    label = urllib.parse.unquote(p.path.lstrip("/"))
    params = {
        "secret": q["secret"][0],
        "digits": int(q.get("digits", ["6"])[0]),
        "period": int(q.get("period", ["30"])[0]),
        "algorithm": q.get("algorithm", ["SHA1"])[0].upper(),
    }
    return label, params


def selftest():
    key1 = b"12345678901234567890"
    key256 = b"12345678901234567890123456789012"
    key512 = b"1234567890123456789012345678901234567890123456789012345678901234"
    keys = (("SHA1", key1), ("SHA256", key256), ("SHA512", key512))
    failures = 0
    for t, v1, v256, v512 in RFC6238_VECTORS:
        for algo, key in keys:
            expect = {"SHA1": v1, "SHA256": v256, "SHA512": v512}[algo]
            got = totp(key, t, 30, 8, algo)
            ok = got == expect
            print("[%s] %-7s T=%-11d got=%s expect=%s"
                  % ("PASS" if ok else "FAIL", algo, t, got, expect))
            failures += 0 if ok else 1
    if failures:
        print("SELFTEST FAILED: %d 项不匹配" % failures, file=sys.stderr)
        return 1
    print("SELFTEST OK: RFC 6238 全部 %d 个向量通过" % (len(RFC6238_VECTORS) * 3))
    return 0


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="TOTP 动态码生成器 (RFC 6238, 兼容 Google Authenticator)")
    ap.add_argument("--secret", help="base32 密钥 (忽略空格/连字符/大小写); 配合 --hex 可按十六进制")
    ap.add_argument("--uri", help="otpauth://totp/... URI (URI 中的参数优先，命令行显式选项再覆盖)")
    ap.add_argument("--hex", dest="hex_mode", action="store_true", help="把 --secret 按十六进制解析")
    ap.add_argument("--digits", type=int, choices=(6, 8), default=None, help="验证码位数 (默认 6)")
    ap.add_argument("--period", type=int, default=None, help="时间步长秒数 (默认 30)")
    ap.add_argument("--algorithm", default=None, help="HMAC 算法 SHA1/SHA256/SHA512 (默认 SHA1)")
    ap.add_argument("--time", type=float, default=None, help="使用的 Unix 时间戳 (秒, 默认当前时间)")
    ap.add_argument("--quiet", action="store_true", help="只输出验证码本身")
    ap.add_argument("--selftest", action="store_true", help="运行 RFC 6238 官方向量自测")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.secret and not args.uri:
        ap.error("需要 --secret 或 --uri (或使用 --selftest)")

    digits, period, algo, label = args.digits, args.period, args.algorithm, ""
    if args.uri:
        try:
            label, p = parse_otpauth(args.uri)
        except ValueError as exc:
            print("URI 解析失败: %s" % exc, file=sys.stderr)
            return 2
        digits = digits if digits is not None else p["digits"]
        period = period if period is not None else p["period"]
        algo = algo if algo is not None else p["algorithm"]
        secret_text = p["secret"]
    else:
        secret_text = args.secret
    digits = digits or 6
    period = period or 30
    algo = (algo or "SHA1").upper()
    if algo not in ALGOS:
        print("不支持的算法: %s (可选 SHA1/SHA256/SHA512)" % algo, file=sys.stderr)
        return 2

    try:
        key = parse_secret(secret_text, args.hex_mode)
    except (ValueError, binascii.Error) as exc:
        print("密钥解析失败: %s" % exc, file=sys.stderr)
        return 2

    when = args.time if args.time is not None else time.time()
    code = totp(key, when, period, digits, algo)
    if args.quiet:
        print(code)
        return 0

    counter = int(when // period)
    print("验证码: %s" % code)
    if label:
        print("账户  : %s" % label)
    print("参数  : %s / %d 位 / %d 秒周期 / 时间步 %d" % (algo, digits, period, counter))
    print("密钥  : base32 %d 字符 (%d 字节)" % (len(secret_text.rstrip("=")), len(key)))
    if args.time is None:
        print("剩余  : %d 秒" % (period - int(when) % period))
    else:
        print("(使用指定时间 %.0f 而非当前时间)" % when)
    return 0


if __name__ == "__main__":
    sys.exit(main())
