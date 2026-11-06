#!/usr/bin/env python3
"""HTTP Digest 认证计算器（RFC 2617，兼容 SHA-256 / *-sess 变体）。

用途：
    按 RFC 2617 规范逐步计算 Digest 认证三要素 HA1 / HA2 / response，
    用于调试、核对客户端构造的 Authorization 头是否与服务端期望一致。

计算规则（H 为 algorithm 对应的哈希函数，默认 MD5）：
    HA1      = H(username:realm:password)
    HA2      = H(method:uri)                        # qop=auth 或无 qop
               H(method:uri:H(entity-body))         # qop=auth-int
    response = H(HA1:nonce:HA2)                           # 无 qop（RFC 2069 兼容）
               H(HA1:nonce:nc:cnonce:qop:HA2)             # 有 qop
    algorithm 为 MD5-sess / SHA-256-sess 时：
    HA1      = H(H(username:realm:password):nonce:cnonce)

示例命令：
    python http-digest-auth.py --selftest
    python http-digest-auth.py --username Mufasa --realm testrealm@host.com \\
        --password "Circle Of Life" --method GET --uri /dir/index.html \\
        --nonce dcd98b7102dd2f0e8b11d0f600bfb0c093 \\
        --cnonce 0a4f113b --nc 00000001 --qop auth
    python http-digest-auth.py -u alice -r corp.example -p s3cret \\
        --method POST --uri /api/login --nonce 6ba9c8 --qop none \\
        --algorithm SHA-256

退出码：0 成功（含 --selftest 全部通过）；1 selftest 失败；2 参数/输入错误。
"""

import argparse
import hashlib
import secrets
import sys

ALGORITHMS = ("MD5", "MD5-sess", "SHA-256", "SHA-256-sess")


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _h(algorithm: str, *parts: str) -> str:
    """按 algorithm 选哈希函数，对冒号拼接的各部分求十六进制摘要。"""
    text = ":".join(parts)
    hasher = hashlib.md5 if algorithm.startswith("MD5") else hashlib.sha256
    return hasher(text.encode("utf-8")).hexdigest()


def compute(username, password, realm, method, uri, nonce,
            cnonce, nc, qop, algorithm, entity_body=""):
    """返回 {"ha1":..., "ha2":..., "response":...}；qop="none" 表示无 qop 路径。"""
    if qop in ("auth", "auth-int") and not (nc and cnonce):
        raise ValueError("qop=auth/auth-int 时必须提供 nc 与 cnonce")
    base_ha1 = _h(algorithm, username, realm, password)
    if algorithm.endswith("-sess"):
        ha1 = _h(algorithm, base_ha1, nonce, cnonce)
    else:
        ha1 = base_ha1
    if qop == "auth-int":
        ha2 = _h(algorithm, method, uri, _h(algorithm, entity_body))
    else:
        ha2 = _h(algorithm, method, uri)
    if qop in ("auth", "auth-int"):
        response = _h(algorithm, ha1, nonce, nc, cnonce, qop, ha2)
    else:
        response = _h(algorithm, ha1, nonce, ha2)
    return {"ha1": ha1, "ha2": ha2, "response": response}


def build_header(username, realm, nonce, uri, algorithm, result,
                 nc=None, cnonce=None, qop=None, opaque=""):
    pairs = [
        f'username="{username}"',
        f'realm="{realm}"',
        f'nonce="{nonce}"',
        f'uri="{uri}"',
        f'algorithm={algorithm}',
    ]
    if qop in ("auth", "auth-int"):
        pairs += [f"qop={qop}", f"nc={nc}", f'cnonce="{cnonce}"']
    if opaque:
        pairs.append(f'opaque="{opaque}"')
    pairs.append(f'response="{result["response"]}"')
    return "Authorization: Digest " + ", ".join(pairs)


def selftest() -> int:
    ok = True

    def check(name, got, want):
        nonlocal ok
        passed = got == want
        ok = ok and passed
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {got}"
              + ("" if passed else f"（期望 {want}）"))

    # RFC 2617 §3.5 示例（response 6629fae4... 为该节给出的公认值）
    r = compute("Mufasa", "Circle Of Life", "testrealm@host.com", "GET",
                "/dir/index.html", "dcd98b7102dd2f0e8b11d0f600bfb0c093",
                "0a4f113b", "00000001", "auth", "MD5")
    check("HA1（RFC2617 §3.5）", r["ha1"], "939e7578ed9e3c518a452acee763bce9")
    check("HA2（RFC2617 §3.5）", r["ha2"], "39aff3a2bab6126f332b942af96d3366")
    check("response（RFC2617 §3.5）", r["response"],
          "6629fae49393a05397450978507c4ef1")

    # 无 qop（RFC 2069 兼容）路径：独立用 hashlib 拼串复算对照
    want = hashlib.md5(b"939e7578ed9e3c518a452acee763bce9"
                       b":dcd98b7102dd2f0e8b11d0f600bfb0c093"
                       b":39aff3a2bab6126f332b942af96d3366").hexdigest()
    r2 = compute("Mufasa", "Circle Of Life", "testrealm@host.com", "GET",
                 "/dir/index.html", "dcd98b7102dd2f0e8b11d0f600bfb0c093",
                 "", "", "none", "MD5")
    check("response（无 qop 路径）", r2["response"], want)

    # qop=auth-int：HA2 = H(method:uri:H(body))，body 为空
    want_ha2 = hashlib.md5(("GET:/dir/index.html:"
                            + hashlib.md5(b"").hexdigest()).encode()).hexdigest()
    r3 = compute("Mufasa", "Circle Of Life", "testrealm@host.com", "GET",
                 "/dir/index.html", "dcd98b7102dd2f0e8b11d0f600bfb0c093",
                 "0a4f113b", "00000001", "auth-int", "MD5")
    check("HA2（qop=auth-int，空 body）", r3["ha2"], want_ha2)

    # MD5-sess：HA1 = H(H(username:realm:password):nonce:cnonce)
    want_ha1s = hashlib.md5(b"939e7578ed9e3c518a452acee763bce9"
                            b":dcd98b7102dd2f0e8b11d0f600bfb0c093"
                            b":0a4f113b").hexdigest()
    r4 = compute("Mufasa", "Circle Of Life", "testrealm@host.com", "GET",
                 "/dir/index.html", "dcd98b7102dd2f0e8b11d0f600bfb0c093",
                 "0a4f113b", "00000001", "auth", "MD5-sess")
    check("HA1（MD5-sess）", r4["ha1"], want_ha1s)

    print("selftest:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


def main(argv=None) -> int:
    _force_utf8_stdio()
    ap = argparse.ArgumentParser(
        description="按 RFC 2617 计算 HTTP Digest 认证的 HA1/HA2/response（调试用）")
    ap.add_argument("--selftest", action="store_true",
                    help="运行内置 RFC 2617 示例自测")
    ap.add_argument("-u", "--username", help="用户名")
    ap.add_argument("-r", "--realm", help="realm（服务端 WWW-Authenticate 中给出）")
    ap.add_argument("-p", "--password", help="口令")
    ap.add_argument("-m", "--method", default="GET", help="HTTP 方法（默认 GET）")
    ap.add_argument("--uri", help="请求 URI（digest-uri）")
    ap.add_argument("--nonce", help="服务端 nonce")
    ap.add_argument("--cnonce", default=None, help="客户端随机串（缺省自动生成）")
    ap.add_argument("--nc", default="00000001", help="nonce 计数（8 位十六进制）")
    ap.add_argument("--qop", choices=("auth", "auth-int", "none"), default="auth",
                    help="qop；none 表示按 RFC 2069 不带 qop 计算")
    ap.add_argument("--algorithm", choices=ALGORITHMS, default="MD5")
    ap.add_argument("--entity-body", default="", help="qop=auth-int 时的请求体文本")
    ap.add_argument("--opaque", default="", help="原样带回的 opaque 参数（可选）")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    missing = [name for name, val in (("--username", args.username),
                                      ("--realm", args.realm),
                                      ("--password", args.password),
                                      ("--uri", args.uri),
                                      ("--nonce", args.nonce)) if val is None]
    if missing:
        ap.error("缺少必填参数：" + " ".join(missing) + "（或使用 --selftest）")
    cnonce = args.cnonce or secrets.token_hex(8)
    try:
        result = compute(args.username, args.password, args.realm, args.method,
                         args.uri, args.nonce, cnonce, args.nc, args.qop,
                         args.algorithm, args.entity_body)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(f"algorithm : {args.algorithm}")
    print(f"HA1       : {result['ha1']}")
    print(f"HA2       : {result['ha2']}")
    print(f"response  : {result['response']}")
    print()
    print(build_header(args.username, args.realm, args.nonce, args.uri,
                       args.algorithm, result, nc=args.nc, cnonce=cnonce,
                       qop=None if args.qop == "none" else args.qop,
                       opaque=args.opaque))
    return 0


if __name__ == "__main__":
    sys.exit(main())
