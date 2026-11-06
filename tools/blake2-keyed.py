#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""blake2-keyed.py —— BLAKE2b / BLAKE2s 带密钥哈希（仅 Python 标准库）。

用途:
    用 hashlib 计算 BLAKE2b（密钥 ≤64 字节，摘要 1~64 字节）或 BLAKE2s
    （密钥 ≤32 字节，摘要 1~32 字节）的带密钥哈希（MAC），支持十六进制
    密钥与 hex/base64/raw 输出；省略密钥时退化为普通 BLAKE2 哈希。

示例命令:
    python blake2-keyed.py "message" -k "secret-key"                  # BLAKE2b，64 字节摘要
    python blake2-keyed.py "message" -k "secret" -a blake2s           # BLAKE2s，32 字节摘要
    python blake2-keyed.py "message" -k "secret" -n 32                # 指定摘要 32 字节
    python blake2-keyed.py "message" --key-hex 000102 --out base64    # 十六进制密钥 + base64
    echo -n data | python blake2-keyed.py -k secret                   # stdin 输入
    python blake2-keyed.py --selftest                                 # 运行内置自测
"""

import argparse
import base64
import hashlib
import sys

# 算法 -> (密钥最大字节数, 摘要最大字节数)
LIMITS = {"blake2b": (64, 64), "blake2s": (32, 32)}

# RFC 7693 / 常用公开向量（无密钥）
VECTORS = {
    ("blake2b", 64, ""):
        "786a02f742015903c6c6fd852552d272912f4740e15847618a86e217f71f5419"
        "d25e1031afee585313896444934eb04b903a685b1448b755d56f701afe9be2ce",
    ("blake2b", 64, "abc"):
        "ba80a53f981c4d0d6a2797b69f12f6e94c212f14685ac4b74b12bb6fdbffa2d1"
        "7d87c5392aab792dc252d5de4533cc9518d38aa8dbf1925ab92386edd4009923",
    ("blake2s", 32, ""):
        "69217a3079908094e11121d042354a7c1f55b6482ca1a51e1b250dfd1ed0eef9",
    ("blake2s", 32, "abc"):
        "508c5e8c327c14e2e1a72ba34eeb452f37458b209ed63a294d999b4c86675982",
}


def _force_utf8_stdio():
    """让输出在非 UTF-8 控制台上也不因中文而报编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_hex_bytes(text):
    """把 '0x00 11:22' 之类的十六进制串解析为 bytes。"""
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


def validate(algo, key, digest_size):
    max_key, max_ds = LIMITS[algo]
    suffix = "b" if algo == "blake2b" else "s"
    if not 1 <= digest_size <= max_ds:
        raise ValueError("BLAKE2{} 摘要长度须为 1~{} 字节，收到 {}".format(suffix, max_ds, digest_size))
    if key is not None and len(key) > max_key:
        raise ValueError("BLAKE2{} 密钥最长 {} 字节，收到 {}".format(suffix, max_key, len(key)))


def compute(algo, data, key, digest_size):
    factory = hashlib.blake2b if algo == "blake2b" else hashlib.blake2s
    return factory(data, key=(b"" if key is None else key), digest_size=digest_size).digest()


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

    for (algo, ds, text), want in sorted(VECTORS.items()):
        got = compute(algo, text.encode("utf-8"), None, ds).hex()
        check(got == want, "{}-{} 无密钥向量 {!r}".format(algo, ds * 8, text or "(空串)"))

    keyed = compute("blake2b", b"payload", b"secret", 64)
    plain = compute("blake2b", b"payload", None, 64)
    check(keyed != plain, "带密钥与无密钥结果不同")
    check(compute("blake2b", b"payload", b"secret", 64) == keyed, "同一密钥结果可复现")
    # 注意：BLAKE2 的参数块包含摘要长度，digest_size 不同则输出完全不同，
    # 不存在 SHAKE 那样的前缀截断一致性，故这里只验证长度与互异性。
    short = compute("blake2b", b"payload", b"secret", 32)
    check(len(short) == 32 and short != keyed,
          "BLAKE2b digest_size=32 输出 32 字节且不同于 64 字节摘要")
    check(len(compute("blake2s", b"payload", b"secret", 17)) == 17,
          "blake2s 自定义摘要长度 17 字节")

    for bad_call, label in [
        (lambda: validate("blake2b", b"k" * 65, 64), "blake2b 密钥 65 字节被拒绝（上限 64）"),
        (lambda: validate("blake2s", None, 33), "blake2s 摘要 33 字节被拒绝（上限 32）"),
        (lambda: validate("blake2b", None, 0), "摘要长度 0 被拒绝"),
    ]:
        try:
            bad_call()
            passed = False
        except ValueError:
            passed = True
        check(passed, label)

    check(parse_hex_bytes("00 11 aa") == b"\x00\x11\xaa", "十六进制密钥解析")
    print("自测结果: {}".format("全部通过" if ok else "存在失败"))
    return 0 if ok else 1


def main(argv=None):
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="blake2-keyed.py",
        description="生成 BLAKE2b/BLAKE2s 带密钥哈希（自定义摘要长度：blake2b 1~64，blake2s 1~32 字节）")
    parser.add_argument("data", nargs="?",
                        help="消息文本（配合 --hex 按十六进制解析；缺省读 stdin）")
    parser.add_argument("-a", "--algo", choices=("blake2b", "blake2s"), default="blake2b",
                        help="BLAKE2 变体（默认 blake2b）")
    parser.add_argument("-k", "--key", help="密钥（UTF-8 文本）；省略则为无密钥哈希")
    parser.add_argument("--key-hex", dest="key_hex", help="密钥（十六进制串）")
    parser.add_argument("-n", "--digest-size", dest="digest_size", type=int, default=None,
                        metavar="N", help="摘要字节数（blake2b 1~64，blake2s 1~32；默认取最大值）")
    parser.add_argument("--hex", dest="as_hex", action="store_true",
                        help="把消息按十六进制字节串解析")
    parser.add_argument("--out", choices=("hex", "base64", "raw"), default="hex",
                        help="输出格式（默认 hex）")
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
        key = None

    max_key, max_ds = LIMITS[args.algo]
    digest_size = max_ds if args.digest_size is None else args.digest_size
    try:
        validate(args.algo, key, digest_size)
    except ValueError as exc:
        parser.error(str(exc))

    msg = read_message(args, parser)
    digest = compute(args.algo, msg, key, digest_size)
    out = format_digest(digest, args.out)
    if out is not None:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
