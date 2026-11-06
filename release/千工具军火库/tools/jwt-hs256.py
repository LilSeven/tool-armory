#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HS256 JWT 签发 / 校验 / 过期检查（纯标准库：hmac + base64url + json）。

用途:
    签发 HS256 JWT（header 为 {"alg":"HS256","typ":"JWT"}），支持注册
    声明 exp（过期）/ nbf（生效）/ iat 以及任意自定义 claim；校验时先用
    hmac.compare_digest 做常数时间签名比较，再检查 exp/nbf（支持容差）。

示例:
    python jwt-hs256.py sign --secret s3cr3t --sub alice --exp-in 3600
    python jwt-hs256.py sign --secret s3cr3t --claim role=admin --claim level=3
    python jwt-hs256.py verify --secret s3cr3t --token <TOKEN> --leeway 30
    python jwt-hs256.py decode --token <TOKEN>      # 不验签，仅供查看

退出码: 0 签发成功或校验通过；1 校验失败（签名不匹配 / 已过期等）；2 参数错误。
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time


def _utf8_stdio():
    """让中文输出在管道/重定向时保持 UTF-8，避免 Windows 本地编码报错。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def b64url_encode(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(text):
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def make_token(payload, secret):
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = b64url_encode(json.dumps(
        header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input += "." + b64url_encode(json.dumps(
        payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"),
                   hashlib.sha256).digest()
    return signing_input + "." + b64url_encode(sig)


def verify_token(token, secret, leeway=0.0, now=None):
    """返回 (ok, 原因, payload)。ok=False 时原因说明失败点。"""
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            return False, "token 应为 3 段 header.payload.signature", None
        header = json.loads(b64url_decode(parts[0]).decode("utf-8"))
        payload = json.loads(b64url_decode(parts[1]).decode("utf-8"))
        sig = b64url_decode(parts[2])
    except (ValueError, UnicodeDecodeError) as e:
        return False, "token 解码失败: %s" % e, None
    if not isinstance(header, dict) or not isinstance(payload, dict):
        return False, "header/payload 必须是 JSON 对象", None
    if header.get("alg") != "HS256":
        return False, "alg=%r 不是 HS256，拒绝校验" % (header.get("alg"),), payload
    signing_input = (parts[0] + "." + parts[1]).encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), signing_input,
                        hashlib.sha256).digest()
    if not hmac.compare_digest(expected, sig):
        return False, "签名不匹配", payload
    now = time.time() if now is None else now
    exp = payload.get("exp")
    if exp is not None:
        if isinstance(exp, bool) or not isinstance(exp, (int, float)):
            return False, "exp 应为数字（Unix 时间戳）", payload
        if now > exp + leeway:
            return False, ("token 已过期（exp=%s，当前约 %d，leeway=%s 秒）"
                           % (exp, int(now), leeway)), payload
    nbf = payload.get("nbf")
    if nbf is not None:
        if isinstance(nbf, bool) or not isinstance(nbf, (int, float)):
            return False, "nbf 应为数字（Unix 时间戳）", payload
        if now + leeway < nbf:
            return False, "token 尚未生效（nbf=%s）" % nbf, payload
    return True, "签名与声明校验通过", payload


def parse_claim(pair):
    key, sep, value = pair.partition("=")
    if not key or not sep:
        raise ValueError("claim 需形如 key=value: %r" % pair)
    try:
        value = json.loads(value)
    except ValueError:
        pass
    return key, value


def _secret_of(args):
    if args.secret_env:
        value = os.environ.get(args.secret_env)
        if not value:
            raise ValueError("环境变量 %s 未设置" % args.secret_env)
        return value
    if args.secret is not None:
        return args.secret
    raise ValueError("必须提供 --secret 或 --secret-env")


def main(argv=None):
    _utf8_stdio()
    ap = argparse.ArgumentParser(description="HS256 JWT 签发/校验工具（纯标准库）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_sign = sub.add_parser("sign", help="签发 token（stdout 只输出 token 本身）")
    p_sign.add_argument("-s", "--secret", help="对称密钥（字符串）")
    p_sign.add_argument("--secret-env", help="从环境变量读取密钥（更安全）")
    p_sign.add_argument("--sub", help="subject 声明")
    p_sign.add_argument("--exp-in", type=int, metavar="SEC",
                        help="多少秒后过期（可为负，便于测试过期）")
    p_sign.add_argument("--nbf-in", type=int, metavar="SEC", help="多少秒后生效")
    p_sign.add_argument("--claim", action="append", default=[], metavar="K=V",
                        help="自定义 claim，可多次；值会尝试按 JSON 解析")

    p_ver = sub.add_parser("verify", help="验签并检查 exp/nbf")
    p_ver.add_argument("-s", "--secret", help="对称密钥（字符串）")
    p_ver.add_argument("--secret-env", help="从环境变量读取密钥")
    p_ver.add_argument("--token", required=True, help="token；'-' 表示从 stdin 读取")
    p_ver.add_argument("--leeway", type=float, default=0.0, metavar="SEC",
                       help="过期/生效检查容差秒数（默认 0）")

    p_dec = sub.add_parser("decode", help="不验签，仅解码查看")
    p_dec.add_argument("--token", required=True)

    args = ap.parse_args(argv)

    if args.cmd == "sign":
        try:
            secret = _secret_of(args)
        except ValueError as e:
            print("错误: %s" % e, file=sys.stderr)
            return 2
        now = int(time.time())
        payload = {"iat": now}
        if args.sub:
            payload["sub"] = args.sub
        if args.exp_in is not None:
            payload["exp"] = now + args.exp_in
        if args.nbf_in is not None:
            payload["nbf"] = now + args.nbf_in
        try:
            for pair in args.claim:
                key, value = parse_claim(pair)
                payload[key] = value
        except ValueError as e:
            print("错误: %s" % e, file=sys.stderr)
            return 2
        print(make_token(payload, secret))
        return 0

    token = args.token
    if token == "-":
        token = sys.stdin.read().strip()

    if args.cmd == "decode":
        try:
            parts = token.split(".")
            header = json.loads(b64url_decode(parts[0]).decode("utf-8"))
            payload = json.loads(b64url_decode(parts[1]).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, IndexError) as e:
            print("错误: token 解码失败: %s" % e, file=sys.stderr)
            return 2
        print("header :")
        print(json.dumps(header, ensure_ascii=False, indent=2, sort_keys=True))
        print("payload:")
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        print("（未验证签名）")
        return 0

    # verify
    try:
        secret = _secret_of(args)
    except ValueError as e:
        print("错误: %s" % e, file=sys.stderr)
        return 2
    ok, reason, payload = verify_token(token, secret, leeway=args.leeway)
    if ok:
        print("校验通过: %s" % reason)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print("校验失败: %s" % reason, file=sys.stderr)
    if payload is not None:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True),
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
