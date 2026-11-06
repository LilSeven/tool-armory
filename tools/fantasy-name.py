#!/usr/bin/env python3
"""fantasy-name.py — 奇幻人名生成: 音节拼接出精灵/矮人/兽人/人类风格的虚构人名(单文件, 仅标准库)。

用途:
    每个种族内置"前缀+中缀+后缀"三段音节库, 拼接成虚拟世界的风格化人名,
    如精灵 Sylariel、矮人 Thorgrim、兽人 Gronak、人类 Aldric。
    名字由音节随机拼合, 可能与任何真实或虚构人物重名, 纯供起名参考。
    --seed 可复现结果。

示例:
    python fantasy-name.py gen                        # 随机 1 个(任意种族)
    python fantasy-name.py gen 5                      # 随机 5 个
    python fantasy-name.py gen 3 --race elf           # 3 个精灵名
    python fantasy-name.py gen 2 --race dwarf --seed 7   # 固定种子复现
    python fantasy-name.py gen 1 --race orc
    python fantasy-name.py gen 1 --race human
    python fantasy-name.py list                       # 查看各族音节库
"""

from __future__ import annotations

import argparse
import random
import sys

RACES = {
    "elf": {
        "label": "精灵",
        "prefix": ["Ael", "Aer", "Cel", "Elo", "Fae", "Gal", "Ith", "Lai",
                   "Mith", "Nym", "Syl", "Thal", "Vae", "Yri"],
        "mid": ["a", "e", "i", "o", "ae", "ia"],
        "suffix": ["riel", "nor", "wen", "wyn", "las", "mir", "drel", "nya"],
    },
    "dwarf": {
        "label": "矮人",
        "prefix": ["Bal", "Bor", "Dain", "Dur", "Grim", "Khar", "Thra",
                   "Thor", "Dun", "Karr", "Mor", "Bru"],
        "mid": ["", "a", "u", "i", "ar", "im", "un"],
        "suffix": ["in", "im", "din", "grim", "lin", "bur", "nor", "dar",
                   "dek", "rik"],
    },
    "orc": {
        "label": "兽人",
        "prefix": ["Gro", "Mug", "Ur", "Zog", "Krug", "Gna", "Dro", "Shag",
                   "Nar", "Uz", "Gor", "Ruk", "Thok", "Mok"],
        "mid": ["", "a", "u", "o"],
        "suffix": ["nak", "gash", "tuk", "rak", "grosh", "zim", "bul",
                   "tar", "dush", "mash"],
    },
    "human": {
        "label": "人类",
        "prefix": ["Al", "Ber", "Cor", "Dre", "Ed", "Fal", "Gar", "Hen",
                   "Jor", "Kel", "Leo", "Mar", "Nor", "Os", "Ro", "Wil"],
        "mid": ["", "a", "e", "i", "o", "er", "an"],
        "suffix": ["ric", "win", "mund", "bert", "dric", "wyn", "stan",
                   "lin", "mar", "ton"],
    },
}

MAX_LEN = 13  # 超长则去掉中缀


def make_name(rng, race):
    """前缀+中缀+后缀 拼一个名字, 首字母大写。"""
    bank = RACES[race]
    pre = rng.choice(bank["prefix"])
    mid = rng.choice(bank["mid"])
    suf = rng.choice(bank["suffix"])
    name = pre + mid + suf
    if len(name) > MAX_LEN:
        name = pre + suf
    return name[0].upper() + name[1:].lower()


def gen_names(rng, count, race):
    names, seen = [], set()
    attempts = 0
    while len(names) < count and attempts < count * 50 + 100:
        attempts += 1
        r = race if race != "any" else rng.choice(sorted(RACES))
        name = make_name(rng, r)
        if name not in seen:
            seen.add(name)
            names.append((name, r))
    return names


def cmd_gen(args):
    if args.race != "any" and args.race not in RACES:
        raise ValueError("种族需为: any/%s" % "/".join(RACES))
    rng = random.Random(args.seed) if args.seed is not None else random.Random()
    for name, r in gen_names(rng, args.count, args.race):
        print("%s (%s)" % (name, RACES[r]["label"]))
    return 0


def cmd_list(args):
    if args.race != "any" and args.race not in RACES:
        raise ValueError("种族需为: any/%s" % "/".join(RACES))
    for key in sorted(RACES):
        if args.race != "any" and key != args.race:
            continue
        bank = RACES[key]
        print("%s (%s)" % (bank["label"], key))
        print("  前缀: %s" % "/".join(bank["prefix"]))
        print("  中缀: %s" % ("/".join(bank["mid"]) or "-"))
        print("  后缀: %s" % "/".join(bank["suffix"]))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="fantasy-name",
        description="音节拼接生成精灵/矮人/兽人风格的虚构人名。")
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="命令")

    sp = sub.add_parser("gen", help="生成虚构人名")
    sp.add_argument("count", nargs="?", type=int, default=1, help="生成个数(默认 1)")
    sp.add_argument("--race", default="any",
                    help="种族: any/%s (默认 any)" % "/".join(RACES))
    sp.add_argument("--seed", type=int, default=None,
                    help="随机种子, 提供则结果可复现")
    sp.set_defaults(func=cmd_gen)

    sp = sub.add_parser("list", help="查看各族音节库")
    sp.add_argument("--race", default="any",
                    help="只看某种族: any/%s" % "/".join(RACES))
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
        print("fantasy-name: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
