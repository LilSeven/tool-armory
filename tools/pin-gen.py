#!/usr/bin/env python3
"""批量 PIN 生成器（secrets 强随机）。

用途：
    批量生成数字 PIN 码，可选规则：无重复数字（每位互不相同）、
    禁相邻重复（如 11）、禁连号（相邻两位差 1，如 12/87）、
    禁整体顺序（如 123456 / 654321），并可指定黑名单 PIN。
    采用 secrets 拒绝采样：生成后校验规则，不满足则重抽。

示例命令：
    python pin-gen.py                            # 10 个 6 位 PIN
    python pin-gen.py -l 4 -c 8                  # 8 个 4 位 PIN
    python pin-gen.py -l 6 --unique-digits       # 6 位且数字互不相同
    python pin-gen.py -l 5 --no-repeat --no-sequential
    python pin-gen.py -l 6 -c 5 --no-ordered --exclude 123456,000000

退出码：
    0 = 成功；2 = 参数错误、规则互相矛盾或规则过严导致无法生成。

仅依赖 Python 标准库：secrets / argparse。
"""

import argparse
import secrets
import sys


def random_pin(length):
    """Return one random numeric string of the given length."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def acceptable(pin, rules):
    """Return True when the candidate satisfies every enabled rule."""
    if pin in rules["exclude"]:
        return False
    if rules["unique_digits"] and len(set(pin)) != len(pin):
        return False
    if rules["no_repeat"] and any(pin[i] == pin[i + 1]
                                  for i in range(len(pin) - 1)):
        return False
    if rules["no_sequential"] and any(
            abs(int(pin[i + 1]) - int(pin[i])) == 1
            for i in range(len(pin) - 1)):
        return False
    if rules["no_ordered"] and len(pin) > 1:
        deltas = [int(pin[i + 1]) - int(pin[i]) for i in range(len(pin) - 1)]
        if all(d == 1 for d in deltas) or all(d == -1 for d in deltas):
            return False
    return True


def generate_pins(count, length, rules, max_attempts=200000):
    """Rejection-sample `count` distinct PINs satisfying `rules`."""
    pins, seen = [], set()
    for _ in range(max_attempts):
        if len(pins) >= count:
            break
        candidate = random_pin(length)
        if candidate in seen:
            continue
        if acceptable(candidate, rules):
            seen.add(candidate)
            pins.append(candidate)
    if len(pins) < count:
        raise RuntimeError(
            "only produced %d of %d PIN(s) after %d attempts; rules are too "
            "tight for length %d" % (len(pins), count, max_attempts, length))
    return pins


def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="pin-gen",
        description="Batch-generate numeric PINs with secrets and optional rules.")
    parser.add_argument("-l", "--length", type=int, default=6,
                        help="PIN length in digits, 1-12 (default %(default)s)")
    parser.add_argument("-c", "--count", type=int, default=10,
                        help="how many PINs (default %(default)s)")
    parser.add_argument("--unique-digits", action="store_true",
                        help="every digit inside one PIN must be different")
    parser.add_argument("--no-repeat", action="store_true",
                        help="forbid identical adjacent digits (e.g. ...11...)")
    parser.add_argument("--no-sequential", action="store_true",
                        help="forbid adjacent digits differing by 1 (e.g. 12 or 87)")
    parser.add_argument("--no-ordered", action="store_true",
                        help="forbid fully ascending/descending PINs (e.g. 123456)")
    parser.add_argument("--exclude", default="", metavar="PINS",
                        help="comma-separated PINs to exclude, e.g. 123456,000000")
    return parser


def main(argv=None):
    try:
        for stream in (sys.stdout, sys.stderr):
            stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    args = build_arg_parser().parse_args(argv)
    if not 1 <= args.length <= 12:
        print("error: --length must be between 1 and 12", file=sys.stderr)
        return 2
    if not 1 <= args.count <= 100000:
        print("error: --count must be between 1 and 100000", file=sys.stderr)
        return 2
    if args.unique_digits and args.length > 10:
        print("error: --unique-digits is impossible for length %d "
              "(only 10 digits exist)" % args.length, file=sys.stderr)
        return 2

    excluded = set()
    if args.exclude:
        for token in args.exclude.split(","):
            token = token.strip()
            if not token.isdigit() or len(token) != args.length:
                print("error: excluded PIN %r must be exactly %d digits"
                      % (token, args.length), file=sys.stderr)
                return 2
            excluded.add(token)

    rules = {
        "exclude": excluded,
        "unique_digits": args.unique_digits,
        "no_repeat": args.no_repeat,
        "no_sequential": args.no_sequential,
        "no_ordered": args.no_ordered,
    }
    try:
        pins = generate_pins(args.count, args.length, rules)
    except RuntimeError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    for pin in pins:
        print(pin)
    print("generated %d PIN(s) of length %d" % (len(pins), args.length),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
