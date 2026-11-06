#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可发音密码生成器 —— 按辅音+元音音节规则生成可朗读、易记忆的随机密码。

用途:
    每个音节 = [声母辅音/辅音串] + 韵母元音/元音串 + [可选韵尾 n/m/l/r/s],
    拼出的字符串基本能照着读, 便于口头转述与记忆; 默认末尾追加 2 位数字
    提升强度。所有随机位取自 secrets 模块(操作系统级密码学安全随机源)。
    默认 4 音节 + 2 位数字约 54 比特熵, 更高安全要求请增大 -s 音节数。

示例命令:
    python pronounceable-password.py                       # 1 个默认密码, 如 komura73
    python pronounceable-password.py -n 5                  # 一次生成 5 个
    python pronounceable-password.py -n 3 -s 4 --cap       # 4 音节、每音节首字母大写
    python pronounceable-password.py -n 3 --sep "-"        # 音节间连字符: ka-ti-mo-ru71
    python pronounceable-password.py -n 2 --symbol         # 末尾追加 1 个特殊符号
    python pronounceable-password.py -n 2 --no-digits      # 纯音节, 不带数字
    python pronounceable-password.py -n 4 --bits           # 行首附估算熵(比特)
"""

import argparse
import math
import secrets
import sys

# 声母: 单辅音 + 常见可朗读辅音串
ONSETS = [
    "b", "c", "d", "f", "g", "h", "j", "k", "l", "m", "n", "p", "r",
    "s", "t", "v", "w", "z",
    "br", "bl", "ch", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "kn",
    "ph", "pl", "pr", "qu", "sc", "sh", "sk", "sl", "sm", "sn", "sp",
    "st", "sw", "th", "tr", "tw", "wh", "wr",
]
# 韵母: 单元音 + 常见元音串
VOWELS = ["a", "e", "i", "o", "u", "ai", "au", "ea", "ee", "ei", "ie", "oa", "oo", "ou"]
# 韵尾: 只用鼻音/流音/擦音, 保证音节不发硬
CODAS = ["n", "m", "l", "r", "s"]
DIGITS = "23456789"          # 剔除易混的 0 和 1
SYMBOLS = "!@#$%^&*-_=+"


def _syllable():
    """随机生成一个音节: [声母] + 韵母 + [韵尾]。"""
    onset = secrets.choice(ONSETS + [""])
    vowel = secrets.choice(VOWELS)
    coda = secrets.choice(CODAS + [""])
    return onset + vowel + coda


def make_password(syllables=4, sep="", cap=False, digits=True, symbol=False):
    """生成一个密码, 返回 (密码文本, 估算熵比特数)。"""
    parts = [_syllable() for _ in range(syllables)]
    if cap:
        parts = [p[:1].upper() + p[1:] for p in parts]
    tail = ""
    if digits:
        tail += secrets.choice(DIGITS) + secrets.choice(DIGITS)
    if symbol:
        tail += secrets.choice(SYMBOLS)
    password = sep.join(parts) + tail

    bits = syllables * (
        math.log2(len(ONSETS) + 1) + math.log2(len(VOWELS)) + math.log2(len(CODAS) + 1)
    )
    if digits:
        bits += 2 * math.log2(len(DIGITS))
    if symbol:
        bits += math.log2(len(SYMBOLS))
    return password, bits


def _utf8_stdio():
    """管道/重定向时强制 UTF-8 输出, 避免 Windows 本地码页乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and not stream.isatty() and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="按辅音+元音音节规则生成可朗读、易记忆的随机密码。")
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="生成数量(默认 1, 上限 10000)")
    parser.add_argument("-s", "--syllables", type=int, default=4,
                        help="每个密码的音节数(默认 4, 范围 1-12)")
    parser.add_argument("--sep", default="", help="音节之间的连接符(默认无, ≤3 字符)")
    parser.add_argument("--cap", action="store_true", help="每个音节首字母大写")
    parser.add_argument("--no-digits", action="store_true", help="末尾不追加数字")
    parser.add_argument("--symbol", action="store_true", help="末尾追加 1 个特殊符号")
    parser.add_argument("--bits", action="store_true", help="每行行首显示估算熵(比特)")
    args = parser.parse_args(argv)

    if not 1 <= args.count <= 10000:
        parser.error("--count 取值范围 1-10000")
    if not 1 <= args.syllables <= 12:
        parser.error("--syllables 取值范围 1-12")
    if len(args.sep) > 3:
        parser.error("--sep 过长(≤3 个字符)")

    for _ in range(args.count):
        password, bits = make_password(
            syllables=args.syllables, sep=args.sep, cap=args.cap,
            digits=not args.no_digits, symbol=args.symbol)
        if args.bits:
            print("%3.0f bits  %s" % (bits, password))
        else:
            print(password)
    return 0


if __name__ == "__main__":
    _utf8_stdio()
    sys.exit(main())
