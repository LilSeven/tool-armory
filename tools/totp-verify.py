#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TOTP 校验器 (RFC 6238)。

校验用户输入的 TOTP 动态码是否有效，默认允许 ±1 个时间窗容差，
以抵御客户端时钟漂移与网络传输延迟。仅供本人账号、授权测试或教学演示使用。

用法 (Windows Git Bash):
  python -I totp-verify.py --secret JBSWY3DPEHPK3PXP --code 123456
  python -I totp-verify.py --secret JBSWY3DPEHPK3PXP --code 123456 --window 2 --digits 8 --period 30
  python -I totp-verify.py --secret GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ --code 94287082 --time 59 --digits 8
  CODE=$(python -I totp-gen.py --secret JBSWY3DPEHPK3PXP --quiet); \
    python -I totp-verify.py --secret JBSWY3DPEHPK3PXP --code "$CODE"
  python -I totp-verify.py --selftest

退出码: 0 = 校验通过/自测通过; 1 = 校验失败/自测失败; 2 = 参数或密钥错误。
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


def hotp(key, counter, digits=6, algo="SHA1"):
    """RFC 4226 HOTP 核心。"""
    digest = hmac.new(key, struct.pack(">Q", counter), ALGOS[algo]).digest()
    offset = digest[-1] & 0x0F
    code = ((digest[offset] & 0x7F) << 24
            | digest[offset + 1] << 16
            | digest[offset + 2] << 8
            | digest[offset + 3]) % (10 ** digits)
    return str(code).zfill(digits)


def verify(key, code, when, period=30, digits=6, algo="SHA1", window=1):
    """返回 (是否有效, 命中的窗口偏移, 当前时间步)。offset: 0=当前窗, -1=上一窗, +1=下一窗。"""
    counter = int(when // period)
    for off in range(-window, window + 1):
        if hmac.compare_digest(hotp(key, counter + off, digits, algo), code):
            return True, off, counter
    return False, None, counter


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
    key = b"12345678901234567890"
    checks = [
        ("RFC6238 向量 (T=59, 8 位) 校验通过", verify(key, "94287082", 59, digits=8)[0] is True),
        ("向量命中的时间窗偏移为 0", verify(key, "94287082", 59, digits=8)[1] == 0),
        ("错误口令被拒绝", not verify(key, "94287083", 59, digits=8)[0]),
        ("+1 时间窗容差命中", verify(key, hotp(key, 2, 8), 59, digits=8, window=1)[1] == 1),
        ("-1 时间窗容差命中", verify(key, hotp(key, 0, 8), 59, digits=8, window=1)[1] == -1),
        ("窗口外口令被拒绝", not verify(key, hotp(key, 5, 8), 59, digits=8, window=1)[0]),
    ]
    failures = 0
    for name, ok in checks:
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
        failures += 0 if ok else 1
    if failures:
        print("SELFTEST FAILED: %d 项" % failures, file=sys.stderr)
        return 1
    print("SELFTEST OK: %d 项全部通过" % len(checks))
    return 0


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="TOTP 校验器 (RFC 6238, 默认允许 ±1 时间窗容差)")
    ap.add_argument("--secret", help="base32 密钥 (忽略空格/连字符/大小写); 配合 --hex 可按十六进制")
    ap.add_argument("--uri", help="otpauth://totp/... URI")
    ap.add_argument("--code", help="待校验的验证码 (纯数字)")
    ap.add_argument("--hex", dest="hex_mode", action="store_true", help="把 --secret 按十六进制解析")
    ap.add_argument("--digits", type=int, choices=(6, 8), default=None, help="验证码位数 (默认 6)")
    ap.add_argument("--period", type=int, default=None, help="时间步长秒数 (默认 30)")
    ap.add_argument("--algorithm", default=None, help="HMAC 算法 SHA1/SHA256/SHA512 (默认 SHA1)")
    ap.add_argument("--window", type=int, default=None, help="允许的时间窗容差 (默认 1, 即 ±1)")
    ap.add_argument("--time", type=float, default=None, help="用于校验的 Unix 时间戳 (秒, 默认当前时间)")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.secret and not args.uri:
        ap.error("需要 --secret 或 --uri (或使用 --selftest)")
    if not args.code:
        ap.error("需要 --code 提供待校验验证码")

    digits, period, algo = args.digits, args.period, args.algorithm
    if args.uri:
        try:
            _, p = parse_otpauth(args.uri)
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
    window = 1 if args.window is None else args.window
    if window < 0 or window > 10:
        print("window 取值应在 0-10 之间", file=sys.stderr)
        return 2

    try:
        key = parse_secret(secret_text, args.hex_mode)
    except (ValueError, binascii.Error) as exc:
        print("密钥解析失败: %s" % exc, file=sys.stderr)
        return 2

    code = re.sub(r"[\s-]+", "", args.code)
    if not re.fullmatch(r"\d+", code):
        print("[无效] 验证码应只含数字 (期望 %d 位)" % digits, file=sys.stderr)
        return 2
    if len(code) != digits:
        print("提示: 输入 %d 位与期望 %d 位不符" % (len(code), digits), file=sys.stderr)

    when = args.time if args.time is not None else time.time()
    ok, off, counter = verify(key, code, when, period, digits, algo, window)
    if ok:
        print("[有效] 验证码匹配，时间窗偏移 %+d (当前时间步 %d，容差 ±%d 窗)"
              % (off, counter, window))
        return 0
    print("[无效] 验证码在 ±%d 时间窗内均不匹配 (当前时间步 %d，%s/%d 位)"
          % (window, counter, algo, digits))
    return 1


if __name__ == "__main__":
    sys.exit(main())
