#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shake-xof.py —— SHAKE128 / SHAKE256 可变长哈希（XOF，仅 Python 标准库）。

用途:
    用 hashlib 的 SHAKE128/SHAKE256 扩展输出函数（XOF）对输入生成
    任意指定字节数（-n/--length）的摘要，支持 hex/base64/raw 输出、
    十六进制输入与 stdin。

示例命令:
    python shake-xof.py "hello" -n 16                      # SHAKE128（默认），16 字节 hex
    python shake-xof.py "hello" -a shake256 -n 64          # SHAKE256，64 字节
    python shake-xof.py --hex deadbeef -n 32 --out base64  # 输入按十六进制字节解析
    echo -n data | python shake-xof.py -n 48               # stdin 输入
    python shake-xof.py --selftest                         # 运行内置自测
"""

import argparse
import base64
import hashlib
import sys

MAX_LENGTH = 1 << 20  # 单次输出上限 1 MiB，防止误用


def _force_utf8_stdio():
    """让输出在非 UTF-8 控制台上也不因中文而报编码错误。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_hex_bytes(text):
    """把 '0xde ad:be' 之类的十六进制串解析为 bytes。"""
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


def factory_for(algo):
    return hashlib.shake_128 if algo == "shake128" else hashlib.shake_256


def compute(algo, data, length):
    return factory_for(algo)(data).digest(length)


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

    for algo in ("shake128", "shake256"):
        factory = factory_for(algo)
        d = factory(b"payload-001").digest(32)
        check(factory(b"payload-001").digest(32) == d,
              "{} 同输入两次计算一致（确定性）".format(algo))
        check(factory(b"payload-001").digest(64)[:32] == d,
              "{} XOF 前缀一致性（64B 输出的前 32B == 32B 输出）".format(algo))
        check(len(factory(b"payload-001").digest(1)) == 1
              and len(factory(b"payload-001").digest(100)) == 100,
              "{} 任意长度输出（1B / 100B）".format(algo))
        check(len(factory(b"x").hexdigest(20)) == 40,
              "{} hexdigest(20) 得 40 个十六进制字符".format(algo))

    check(hashlib.shake_128(b"m").digest(32) != hashlib.shake_256(b"m").digest(32),
          "SHAKE128 与 SHAKE256 输出互不相同")
    print("自测结果: {}".format("全部通过" if ok else "存在失败"))
    return 0 if ok else 1


def main(argv=None):
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="shake-xof.py",
        description="用 SHAKE128/SHAKE256 XOF 输出任意指定长度的哈希摘要")
    parser.add_argument("data", nargs="?",
                        help="消息文本（配合 --hex 按十六进制解析；缺省读 stdin）")
    parser.add_argument("-a", "--algo", choices=("shake128", "shake256"), default="shake128",
                        help="XOF 算法（默认 shake128）")
    parser.add_argument("-n", "--length", type=int, default=32, metavar="N",
                        help="输出摘要字节数（1~1048576，默认 32）")
    parser.add_argument("--hex", dest="as_hex", action="store_true",
                        help="把消息按十六进制字节串解析")
    parser.add_argument("--out", choices=("hex", "base64", "raw"), default="hex",
                        help="输出格式（默认 hex）")
    parser.add_argument("--selftest", action="store_true", help="运行内置自测并退出")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    if not 1 <= args.length <= MAX_LENGTH:
        parser.error("--length 须在 1~{} 字节之间".format(MAX_LENGTH))

    msg = read_message(args, parser)
    digest = compute(args.algo, msg, args.length)
    out = format_digest(digest, args.out)
    if out is not None:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
