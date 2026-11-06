#!/usr/bin/env python3
"""base62-tool.py — 自实现的 Base62/Base36 编解码工具(单文件, 仅标准库)。

用途:
    在整数 / 字节串(及 UTF-8 文本、十六进制串)与 Base62、Base36 字符串之间互相转换,
    适合生成短号、短 ID。字母表:
        Base62 = 0-9 a-z A-Z(区分大小写)
        Base36 = 0-9 a-z(解码时忽略大小写)
    字节串按大端大整数编码, 每个 0x00 前导字节映射为一个前导 '0' 字符, 可无损往返。

示例:
    python base62-tool.py enc-int 12345           # -> 3d7
    python base62-tool.py dec-int 3d7             # -> 12345
    python base62-tool.py enc-int 12345 --base36  # -> 9ix
    python base62-tool.py enc-hex 4869            # -> 4OZ
    python base62-tool.py dec-hex 4OZ             # -> 4869
    python base62-tool.py enc-text "Hello, World!"
    python base62-tool.py dec-text <上一步输出的编码串>   # 还原文本
    python base62-tool.py new-code 10             # 随机 10 位短号
"""

from __future__ import annotations

import argparse
import secrets
import sys

B62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
B36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def int_to_base(n, alpha):
    """非负整数 -> base 编码串。"""
    if n < 0:
        raise ValueError("negative integers not supported")
    if n == 0:
        return alpha[0]
    base = len(alpha)
    digits = []
    while n:
        n, r = divmod(n, base)
        digits.append(alpha[r])
    return "".join(reversed(digits))


def base_to_int(s, alpha, ci=False):
    """base 编码串 -> 整数。ci=True 时忽略大小写(用于 Base36)。"""
    if not s:
        raise ValueError("empty string")
    table = {c: i for i, c in enumerate(alpha)}
    if ci:
        for c, i in list(table.items()):
            table[c.upper()] = i
    n = 0
    for ch in s:
        try:
            n = n * len(alpha) + table[ch]
        except KeyError:
            raise ValueError("invalid character %r for base %d" % (ch, len(alpha))) from None
    return n


def bytes_to_base(data, alpha):
    """字节串 -> base 编码串: 前导 0x00 字节 -> 前导 '0' 字符, 其余按大整数编码。

    空字节串编码为空串(从而 b"\\x00" 唯一对应 "0", 往返无损)。
    """
    if not data:
        return ""
    zeros = len(data) - len(data.lstrip(b"\x00"))
    n = int.from_bytes(data, "big")
    body = int_to_base(n, alpha) if n else ""
    return alpha[0] * zeros + body


def base_to_bytes(s, alpha, ci=False):
    """base 编码串 -> 字节串(bytes_to_base 的逆变换)。"""
    zero_char = alpha[0]
    zeros = len(s) - len(s.lstrip(zero_char))
    body = s[zeros:]
    n = base_to_int(body, alpha, ci) if body else 0
    if n == 0:
        return b"\x00" * zeros
    return b"\x00" * zeros + n.to_bytes((n.bit_length() + 7) // 8, "big")


def parse_hex(text):
    """十六进制串 -> 字节串; 容忍空格、冒号分隔与 0x 前缀。"""
    t = "".join(text.split()).lower().replace(":", "")
    if t.startswith("0x"):
        t = t[2:]
    if not t or len(t) % 2:
        raise ValueError("hex string must have even length: %r" % text)
    try:
        return bytes.fromhex(t)
    except ValueError:
        raise ValueError("invalid hex character: %r" % text) from None


def _alpha(args):
    return B36 if args.base36 else B62


def _read_stdin_text():
    return sys.stdin.buffer.read().decode("utf-8", "replace").strip()


def _pick(args, own, fallback_stdin=True):
    """取位置参数; 省略或 '-' 时改读 stdin。"""
    if own not in (None, "-"):
        return own
    if fallback_stdin:
        return _read_stdin_text()
    raise ValueError("缺少输入(传参或经 stdin 管道提供)")


def cmd_enc_int(args):
    print(int_to_base(args.value, _alpha(args)))
    return 0


def cmd_dec_int(args):
    s = _pick(args, args.value).strip()
    print(base_to_int(s, _alpha(args), args.base36))
    return 0


def cmd_enc_text(args):
    text = _pick(args, args.text)
    print(bytes_to_base(text.encode("utf-8"), _alpha(args)))
    return 0


def cmd_dec_text(args):
    s = _pick(args, args.code).strip()
    print(base_to_bytes(s, _alpha(args), args.base36).decode("utf-8"))
    return 0


def cmd_enc_hex(args):
    print(bytes_to_base(parse_hex(args.hexstr), _alpha(args)))
    return 0


def cmd_dec_hex(args):
    s = _pick(args, args.code).strip()
    print(base_to_bytes(s, _alpha(args), args.base36).hex())
    return 0


def cmd_new_code(args):
    if args.length < 1:
        raise ValueError("code length must be >= 1")
    alpha = _alpha(args)
    print("".join(secrets.choice(alpha) for _ in range(args.length)))
    return 0


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--base36", action="store_true",
                        help="使用 Base36 字母表(默认 Base62)")

    parser = argparse.ArgumentParser(
        prog="base62-tool",
        description="Base62/Base36 与整数、字节串互转, 可做短号编码。",
        parents=[common])
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="命令")

    sp = sub.add_parser("enc-int", parents=[common], help="整数 -> 编码串")
    sp.add_argument("value", type=int, help="非负整数")
    sp.set_defaults(func=cmd_enc_int)

    sp = sub.add_parser("dec-int", parents=[common], help="编码串 -> 整数")
    sp.add_argument("value", nargs="?", default=None, help="编码串; 省略或 '-' 时读 stdin")
    sp.set_defaults(func=cmd_dec_int)

    sp = sub.add_parser("enc-text", parents=[common], help="UTF-8 文本 -> 编码串")
    sp.add_argument("text", nargs="?", default=None, help="文本; 省略或 '-' 时读 stdin")
    sp.set_defaults(func=cmd_enc_text)

    sp = sub.add_parser("dec-text", parents=[common], help="编码串 -> UTF-8 文本")
    sp.add_argument("code", nargs="?", default=None, help="编码串; 省略或 '-' 时读 stdin")
    sp.set_defaults(func=cmd_dec_text)

    sp = sub.add_parser("enc-hex", parents=[common], help="十六进制串 -> 编码串")
    sp.add_argument("hexstr", help="如 4869 / de:ad:be:ef / 0xdeadbeef")
    sp.set_defaults(func=cmd_enc_hex)

    sp = sub.add_parser("dec-hex", parents=[common], help="编码串 -> 十六进制串")
    sp.add_argument("code", nargs="?", default=None, help="编码串; 省略或 '-' 时读 stdin")
    sp.set_defaults(func=cmd_dec_hex)

    sp = sub.add_parser("new-code", parents=[common], help="生成随机短号(密码学安全随机)")
    sp.add_argument("length", type=int, help="短号长度")
    sp.set_defaults(func=cmd_new_code)
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, UnicodeDecodeError) as exc:
        print("base62-tool: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
