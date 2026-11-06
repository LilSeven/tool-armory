#!/usr/bin/env python3
"""随机密码生成器（Python secrets 加密级随机源）。

用途：
    按规则生成强随机密码：可指定长度与数量，选择启用的字符类别
    （大写 / 小写 / 数字 / 符号），排除易混淆的歧义字符（Il1O0o），
    自定义符号集与排除字符；默认保证密码中每个启用的类别至少出现
    一次，并用 secrets 驱动的 Fisher-Yates 洗牌打乱顺序。

示例命令：
    python password-gen.py                        # 16 位，默认全类别
    python password-gen.py -l 24 -c 5             # 24 位，生成 5 个
    python password-gen.py -l 20 --no-symbols     # 不含符号
    python password-gen.py -l 20 --no-ambiguous   # 排除 Il1O0o
    python password-gen.py -l 12 --exclude-chars aeiou019
    python password-gen.py -l 16 --symbols '!@#*?' --no-require-each

退出码：
    0 = 成功；2 = 参数或约束错误（如长度不足以容纳各类别）。

仅依赖 Python 标准库：secrets / string / argparse / math。
"""

import argparse
import math
import secrets
import string
import sys

UPPER = string.ascii_uppercase
LOWER = string.ascii_lowercase
DIGITS = string.digits
DEFAULT_SYMBOLS = "!@#$%^&*()-_=+[]{}<>?/|~.,;:"
AMBIGUOUS = "Il1O0o"


def secure_shuffle(items):
    """In-place Fisher-Yates shuffle driven by secrets.randbelow."""
    for i in range(len(items) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        items[i], items[j] = items[j], items[i]


def filter_class(chars, exclude_chars="", no_ambiguous=False):
    """Keep only chars not excluded (and not ambiguous, if requested)."""
    return "".join(
        ch for ch in chars
        if ch not in exclude_chars and not (no_ambiguous and ch in AMBIGUOUS)
    )


def generate_password(length, classes, require_each=True):
    """classes: [(name, chars)] with non-empty chars; returns one password."""
    pool = "".join(chars for _, chars in classes)
    picked = []
    if require_each:
        for _, chars in classes:
            picked.append(secrets.choice(chars))
    while len(picked) < length:
        picked.append(secrets.choice(pool))
    secure_shuffle(picked)
    return "".join(picked)


def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="password-gen",
        description="Generate strong random passwords using secrets (stdlib only).")
    parser.add_argument("-l", "--length", type=int, default=16,
                        help="password length (default %(default)s)")
    parser.add_argument("-c", "--count", type=int, default=1,
                        help="how many passwords to generate (default %(default)s)")
    parser.add_argument("--no-upper", action="store_true",
                        help="exclude uppercase letters")
    parser.add_argument("--no-lower", action="store_true",
                        help="exclude lowercase letters")
    parser.add_argument("--no-digits", action="store_true", help="exclude digits")
    parser.add_argument("--no-symbols", action="store_true", help="exclude symbols")
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS, metavar="SET",
                        help="custom symbol set (default: %s)" % DEFAULT_SYMBOLS)
    parser.add_argument("--exclude-chars", default="", metavar="CHARS",
                        help="characters to exclude from every class")
    parser.add_argument("--no-ambiguous", action="store_true",
                        help="exclude look-alike characters (%s)" % AMBIGUOUS)
    parser.add_argument("--no-require-each", action="store_true",
                        help="do not force at least one char from each enabled class")
    return parser


def main(argv=None):
    try:
        for stream in (sys.stdout, sys.stderr):
            stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    args = build_arg_parser().parse_args(argv)
    if not 1 <= args.length <= 512:
        print("error: --length must be between 1 and 512", file=sys.stderr)
        return 2
    if not 1 <= args.count <= 1000:
        print("error: --count must be between 1 and 1000", file=sys.stderr)
        return 2

    wanted = []
    if not args.no_upper:
        wanted.append(("upper", UPPER))
    if not args.no_lower:
        wanted.append(("lower", LOWER))
    if not args.no_digits:
        wanted.append(("digits", DIGITS))
    if not args.no_symbols:
        wanted.append(("symbols", args.symbols))

    classes = []
    for name, chars in wanted:
        kept = filter_class(chars, args.exclude_chars, args.no_ambiguous)
        if not kept:
            print("error: class '%s' is empty after exclusions" % name,
                  file=sys.stderr)
            return 2
        classes.append((name, kept))

    require_each = not args.no_require_each
    if require_each and args.length < len(classes):
        print("error: length %d cannot contain one char from each of the %d "
              "enabled classes" % (args.length, len(classes)), file=sys.stderr)
        return 2

    pool = "".join(chars for _, chars in classes)
    bits = args.length * math.log2(len(pool))
    for _ in range(args.count):
        print(generate_password(args.length, classes, require_each=require_each))
    print("generated %d password(s): length=%d pool=%d chars, ~%.1f bits each"
          % (args.count, args.length, len(pool), bits), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
