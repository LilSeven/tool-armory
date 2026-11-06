#!/usr/bin/env python3
"""模板密码生成器（占位符逐位生成）。

用途：
    按模板逐位生成密码：L=大写字母，l=小写字母，d/D=数字，s/S=符号；
    模板中的其他字符按字面输出（如 '-'）。随机源为 secrets，支持
    自定义符号集、排除字符与排除歧义字符（Il1O0o）。

    注意：小写 s 是符号占位符，模板中无法输出字面的小写 s。

示例命令：
    python pattern-password.py 'Lll-Ddd-S'        # 例如：Kqv-307-!
    python pattern-password.py 'Llllll-dddd-ss' -c 5
    python pattern-password.py 'Ldl-dld-sL' --no-ambiguous
    python pattern-password.py 'LLL-DDD-SSS' --symbols '!@#$%'

退出码：
    0 = 成功；2 = 参数错误、模板无占位符或某类字符集被排空。

仅依赖 Python 标准库：secrets / string / argparse。
"""

import argparse
import secrets
import string
import sys

UPPER = string.ascii_uppercase
LOWER = string.ascii_lowercase
DIGITS = string.digits
DEFAULT_SYMBOLS = "!@#$%^&*()-_=+[]{}<>?/|~.,;:"
AMBIGUOUS = "Il1O0o"

# placeholder char -> class name; any other character in the pattern is literal
CLASS_OF = {"L": "upper", "l": "lower", "D": "digit", "d": "digit",
            "S": "symbol", "s": "symbol"}


def filter_set(chars, exclude_chars="", no_ambiguous=False):
    """Keep only chars not excluded (and not ambiguous, if requested)."""
    return "".join(
        ch for ch in chars
        if ch not in exclude_chars and not (no_ambiguous and ch in AMBIGUOUS)
    )


def generate_from_pattern(pattern, classes):
    """classes: {class_name: non-empty chars}; literal chars pass through."""
    out = []
    for ch in pattern:
        cls = CLASS_OF.get(ch)
        out.append(secrets.choice(classes[cls]) if cls else ch)
    return "".join(out)


def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="pattern-password",
        description="Generate passwords from a template: L=uppercase, l=lowercase, "
                    "d/D=digit, s/S=symbol; any other character is literal.")
    parser.add_argument("pattern", help="template, e.g. 'Lll-Ddd-S'")
    parser.add_argument("-c", "--count", type=int, default=1,
                        help="how many passwords (default %(default)s)")
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS, metavar="SET",
                        help="custom symbol set (default: %s)" % DEFAULT_SYMBOLS)
    parser.add_argument("--exclude-chars", default="", metavar="CHARS",
                        help="characters to exclude from every class")
    parser.add_argument("--no-ambiguous", action="store_true",
                        help="exclude look-alike characters (%s)" % AMBIGUOUS)
    return parser


def main(argv=None):
    try:
        for stream in (sys.stdout, sys.stderr):
            stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    args = build_arg_parser().parse_args(argv)
    if not 1 <= args.count <= 1000:
        print("error: --count must be between 1 and 1000", file=sys.stderr)
        return 2
    if not args.pattern:
        print("error: pattern must not be empty", file=sys.stderr)
        return 2

    used = {CLASS_OF[ch] for ch in args.pattern if ch in CLASS_OF}
    if not used:
        print("error: pattern has no placeholder "
              "(use any of L l d D s S)", file=sys.stderr)
        return 2

    sources = {"upper": UPPER, "lower": LOWER, "digit": DIGITS,
               "symbol": args.symbols}
    classes = {}
    for name in sorted(used):
        kept = filter_set(sources[name], args.exclude_chars, args.no_ambiguous)
        if not kept:
            print("error: class '%s' is empty after exclusions" % name,
                  file=sys.stderr)
            return 2
        classes[name] = kept

    for _ in range(args.count):
        print(generate_from_pattern(args.pattern, classes))
    print("generated %d password(s) from pattern %r (classes: %s)"
          % (args.count, args.pattern, ",".join(sorted(used))), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
