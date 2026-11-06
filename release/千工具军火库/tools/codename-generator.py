#!/usr/bin/env python3
"""codename-generator.py — 项目代号生成器: 形容词+名词组合出 amber-falcon 风格代号(单文件, 仅标准库)。

用途:
    用"形容词+名词"两段内置词库(各 32 个, 共 1024 种组合)拼出项目代号,
    如 amber-falcon、midnight-compass。支持四种书写风格与自定义分隔符,
    --seed 可复现结果。

示例:
    python codename-generator.py gen                    # 随机 1 个(默认 kebab 风)
    python codename-generator.py gen 5                  # 随机 5 个
    python codename-generator.py gen 3 --seed 42        # 固定种子, 结果可复现
    python codename-generator.py gen 1 --style pascal   # AmberFalcon
    python codename-generator.py gen 1 --style snake    # amber_falcon
    python codename-generator.py gen 1 --style upper    # AMBER_FALCON
    python codename-generator.py gen 1 --style kebab --sep "+"  # amber+falcon
    python codename-generator.py list                   # 查看词库
"""

from __future__ import annotations

import argparse
import random
import sys

ADJECTIVES = [
    "amber", "azure", "bronze", "cobalt", "copper", "crimson", "dusty",
    "ember", "flint", "golden", "granite", "iron", "ivory", "jade",
    "lunar", "midnight", "misty", "onyx", "paper", "quiet", "ruby",
    "rustic", "scarlet", "silent", "silver", "slate", "solar", "stone",
    "stormy", "velvet", "violet", "woven",
]

NOUNS = [
    "falcon", "heron", "kestrel", "otter", "raven", "lynx", "badger",
    "marmot", "tiger", "walrus", "atlas", "beacon", "compass", "vortex",
    "prism", "harbor", "lighthouse", "anthem", "orchid", "glacier",
    "monsoon", "quarry", "canyon", "meadow", "birch", "cedar", "delta",
    "echo", "fathom", "gale", "herald", "summit",
]

STYLES = ("kebab", "snake", "space", "pascal", "upper")
DEFAULT_SEP = {"kebab": "-", "snake": "_", "space": " ", "upper": "_"}


def format_codename(adj, noun, style, sep=None):
    """按风格拼一代号; pascal 不用分隔符, 其余风格可用 --sep 覆盖默认分隔符。"""
    if style == "pascal":
        return adj.capitalize() + noun.capitalize()
    s = sep if sep is not None else DEFAULT_SEP[style]
    code = adj + s + noun
    if style == "upper":
        code = code.upper()
    return code


def gen_codenames(rng, count, style, sep):
    combos = [(a, n) for a in ADJECTIVES for n in NOUNS]
    if count > len(combos):
        raise ValueError("最多 %d 个不重复代号(词库组合共 %d 种)"
                         % (len(combos), len(combos)))
    picked = rng.sample(combos, count)
    return [format_codename(a, n, style, sep) for a, n in picked]


def cmd_gen(args):
    rng = random.Random(args.seed) if args.seed is not None else random.Random()
    for code in gen_codenames(rng, args.count, args.style, args.sep):
        print(code)
    return 0


def cmd_list(args):
    print("形容词 %d 个: %s" % (len(ADJECTIVES), ", ".join(ADJECTIVES)))
    print("名词 %d 个: %s" % (len(NOUNS), ", ".join(NOUNS)))
    print("组合空间 %d x %d = %d 种; 风格: %s"
          % (len(ADJECTIVES), len(NOUNS), len(ADJECTIVES) * len(NOUNS),
             "/".join(STYLES)))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="codename-generator",
        description="形容词+名词组合生成 amber-falcon 风格项目代号。")
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="命令")

    sp = sub.add_parser("gen", help="生成项目代号")
    sp.add_argument("count", nargs="?", type=int, default=1, help="生成个数(默认 1)")
    sp.add_argument("--style", choices=STYLES, default="kebab",
                    help="书写风格: kebab=amber-falcon, snake=amber_falcon, "
                         "space='amber falcon', pascal=AmberFalcon, upper=AMBER_FALCON")
    sp.add_argument("--sep", default=None,
                    help="覆盖分隔符(仅非 pascal 风格生效)")
    sp.add_argument("--seed", type=int, default=None,
                    help="随机种子, 提供则结果可复现")
    sp.set_defaults(func=cmd_gen)

    sp = sub.add_parser("list", help="查看词库与组合空间")
    sp.set_defaults(func=cmd_list)
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
    except ValueError as exc:
        print("codename-generator: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
