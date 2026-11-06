#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hmac-tool.py —— HMAC 消息认证码生成与安全比对（仅 Python 标准库）。

用途:
    基于 hmac 模块生成 HMAC 认证码（默认 HMAC-SHA256，可选 md5/sha1/
    sha224/sha384/sha512/sha3/blake2 等），支持十六进制密钥、输出截断
    （-n/--truncate N 字节）与 hex/base64/raw 输出；--compare 使用
    hmac.compare_digest 做恒定时间安全比对（匹配退出码 0，不匹配 1），
    避免时序侧信道泄露。

示例命令:
    python hmac-tool.py "hello" -k secret                          # HMAC-SHA256，十六进制
    python hmac-tool.py "hello" -k secret -a sha512                # 更换哈希算法
    python hmac-tool.py "hello" --key-hex 0a1b2c                   # 十六进制密钥（--key-hex 需带值）
    python hmac-tool.py "hello" -k secret -n 16 --out base64       # 截断 16 字节，base64 输出
    echo -n msg | python hmac-tool.py -k secret                    # 消息从 stdin 读取
    python hmac-tool.py "hello" -k secret --compare <期望hex>       # 安全比对
    python hmac-tool.py --selftest                                 # 运行内置自测
"""

import argparse
import base64
import hmac
import sys

ALGOS = ("md5", "sha1", "sha224", "sha256", "sha384", "sha512",
         "sha3_224", "sha3_256", "sha3_384", "sha3_512",
         "blake2b", "blake2s")


def _force_utf8_stdio():
    """让输出在非 UTF-8 控制台上也不因中文而报编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_hex_bytes(text):
    """把 '0x0a 1b:2c' 之类的十六进制串解析为 bytes。"""
    cleaned = text.strip()
    if cleaned.lower().startswith("0x"):
        cleaned = cleaned[2:]
    cleaned = "".join(cleaned.split()).replace(":", "")
    if len(cleaned) % 2 != 0:
        raise ValueError("十六进制串长度须为偶数: {!r}".format(text))
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ValueError("非法十六进制串: {!r}".format(text)) from exc


def compute_digest(algo, key, msg, nbytes=None):
    mac = hmac.new(key, msg, digestmod=algo)
    digest = mac.digest()
    if nbytes is not None:
        digest = digest[:nbytes]
    return digest


def format_digest(digest, out):
    if out == "raw":
        sys.stdout.buffer.write(digest)
        sys.stdout.buffer.flush()
        return None
    if out == "base64":
        return base64.b64encode(digest).decode("ascii")
    return digest.hex()


def read_message(args, parser):
    if args.data is not None:
        if args.as_hex:
            try:
                return parse_hex_bytes(args.data)
            except ValueError as exc:
                parser.error(str(exc))
        return args.data.encode("utf-8")
    if sys.stdin.isatty():
        parser.error("缺少消息：请传入 data 参数或用管道送入 stdin")
    return sys.stdin.buffer.read()


def selftest():
    ok = True

    def check(cond, label):
        nonlocal ok
        ok = ok and bool(cond)
        print("[{}] {}".format("PASS" if cond else "FAIL", label))

    cases = [
        ("HMAC-SHA256 (示例向量)", "sha256", b"key",
         b"The quick brown fox jumps over the lazy dog",
         "f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8"),
        ("HMAC-SHA256 (RFC 4231 TC2)", "sha256", b"Jefe",
         b"what do ya want for nothing?",
         "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"),
        ("HMAC-SHA512 (RFC 4231 TC1)", "sha512", b"\x0b" * 20, b"Hi There",
         "87aa7cdea5ef619d4ff0b4241a1d6cb02379f4e2ce4ec2787ad0b30545e17cdedaa833b7d6b8a702038b274eaea3f4e4be9d914eeb61f1702e696c203a126854"),
        ("HMAC-MD5 (RFC 2202 TC2)", "md5", b"Jefe",
         b"what do ya want for nothing?",
         "750c783e6ab0b503eaa86e310a5db738"),
    ]
    for label, algo, key, msg, want in cases:
        got = compute_digest(algo, key, msg).hex()
        check(got == want, "{}\n      got ={}\n      want={}".format(label, got, want))

    check(hmac.compare_digest(b"aaa", b"aaa") and not hmac.compare_digest(b"aaa", b"aab"),
          "hmac.compare_digest 相等/不等判定")
    check(len(compute_digest("sha256", b"k", b"m", 16)) == 16,
          "--truncate 16 -> 输出 16 字节")
    check(parse_hex_bytes("00 11 aa") == b"\x00\x11\xaa"
          and parse_hex_bytes("0x0a1b") == b"\x0a\x1b",
          "十六进制密钥/消息解析")
    print("自测结果: {}".format("全部通过" if ok else "存在失败"))
    return 0 if ok else 1


def main(argv=None):
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="hmac-tool.py",
        description="用 hmac 模块生成 HMAC 认证码，并用 compare_digest 做安全比对")
    parser.add_argument("data", nargs="?",
                        help="消息文本（配合 --hex 按十六进制解析；缺省读 stdin）")
    parser.add_argument("-k", "--key", help="密钥（UTF-8 文本）")
    parser.add_argument("--key-hex", dest="key_hex", help="密钥（十六进制串）")
    parser.add_argument("-a", "--algo", choices=ALGOS, default="sha256",
                        help="哈希算法（默认 sha256）")
    parser.add_argument("--hex", dest="as_hex", action="store_true",
                        help="把消息按十六进制字节串解析")
    parser.add_argument("-n", "--truncate", type=int, default=None, metavar="N",
                        help="截断输出到 N 字节")
    parser.add_argument("--out", choices=("hex", "base64", "raw"), default="hex",
                        help="输出格式（默认 hex）")
    parser.add_argument("--compare", metavar="HEX", default=None,
                        help="用 hmac.compare_digest 与期望摘要（十六进制）安全比对")
    parser.add_argument("--selftest", action="store_true", help="运行内置自测并退出")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    if args.key_hex is not None:
        try:
            key = parse_hex_bytes(args.key_hex)
        except ValueError as exc:
            parser.error(str(exc))
    elif args.key is not None:
        key = args.key.encode("utf-8")
    else:
        parser.error("必须提供密钥：-k/--key 或 --key-hex")

    msg = read_message(args, parser)
    mac = hmac.new(key, msg, digestmod=args.algo)
    full = mac.digest_size
    if args.truncate is not None and not 1 <= args.truncate <= full:
        parser.error("--truncate 取值须在 1~{}（{} 摘要为 {} 字节）".format(full, args.algo, full))
    digest = mac.digest() if args.truncate is None else mac.digest()[:args.truncate]

    if args.compare is not None:
        try:
            expected = parse_hex_bytes(args.compare)
        except ValueError as exc:
            parser.error(str(exc))
        match = hmac.compare_digest(digest, expected)
        print("MATCH" if match else "MISMATCH")
        return 0 if match else 1

    out = format_digest(digest, args.out)
    if out is not None:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
