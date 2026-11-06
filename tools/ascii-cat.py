#!/usr/bin/env python3
"""猫狗字符画（ascii-cat）—— 随机输出一只 ASCII 猫/狗/兔，支持心情变体。

用途:
    随机（或指定）画一只 ASCII 小动物：猫 / 狗 / 兔；
    心情（happy 开心 / grumpy 生气 / sleepy 犯困）决定表情变体。
    仅用 Python 标准库，单文件即可运行。

示例命令:
    python -I ascii-cat.py                            # 随机动物 + 随机心情
    python -I ascii-cat.py --animal cat --mood happy --seed 3
    python -I ascii-cat.py --animal dog --mood 生气
    python -I ascii-cat.py --animal 兔 --mood sleepy --seed 9

参数:
    --animal  cat|dog|rabbit|猫|狗|兔             动物（缺省随机）
    --mood    happy|grumpy|sleepy|开心|生气|犯困  心情（缺省随机）
    --seed N  随机种子（可复现）
"""

import argparse
import random
import sys

ANIMALS = {"cat": "猫", "dog": "狗", "rabbit": "兔"}
MOODS = {"happy": "开心", "grumpy": "生气", "sleepy": "犯困"}

ARTS = {
    ("cat", "happy"): (
        "开心的猫",
        [r" /\_/\ ", r"( ^.^ )", r" > ^ <"],
    ),
    ("cat", "grumpy"): (
        "生气的猫",
        [r" /\_/\ ", r"( >.< )", r" /|   |\ "],
    ),
    ("cat", "sleepy"): (
        "犯困的猫",
        [r" /\_/\ ", r"( -.- )", r"  z Z z"],
    ),
    ("dog", "happy"): (
        "开心的狗",
        [r" __      __", r"o'')}____//", r" `_/      )", r" (_(_/-(_/"],
    ),
    ("dog", "grumpy"): (
        "生气的狗",
        [r" __      __", r">'')}____//", r" `_/      )", r" (_(_/-(_/"],
    ),
    ("dog", "sleepy"): (
        "犯困的狗",
        [r" __      __", r"-'')}____//", r" `_/      )", r" (_(_/-(_/", r"   z Z z"],
    ),
    ("rabbit", "happy"): (
        "开心的兔",
        [r" (\_/)", r" (^.^)", r' o_(")(")'],
    ),
    ("rabbit", "grumpy"): (
        "生气的兔",
        [r" (\_/)", r" (>.<)", r' o_(")(")'],
    ),
    ("rabbit", "sleepy"): (
        "犯困的兔",
        [r" (\_/)", r" (-.-)", r' o_(")(")', r"  z Z z"],
    ),
}

ANIMAL_ALIASES = {
    "cat": "cat", "猫": "cat",
    "dog": "dog", "狗": "dog",
    "rabbit": "rabbit", "兔": "rabbit", "兔子": "rabbit",
}
MOOD_ALIASES = {
    "happy": "happy", "开心": "happy",
    "grumpy": "grumpy", "生气": "grumpy", "暴躁": "grumpy",
    "sleepy": "sleepy", "困": "sleepy", "犯困": "sleepy",
}


def _norm(raw, aliases):
    return aliases.get(raw.strip().lower())


def build_parser():
    p = argparse.ArgumentParser(
        prog="ascii-cat", description="随机输出一只 ASCII 猫/狗/兔字符画（带心情变体）"
    )
    p.add_argument("--animal", help="动物: cat|dog|rabbit 或 猫|狗|兔，缺省随机")
    p.add_argument("--mood", help="心情: happy|grumpy|sleepy 或 开心|生气|犯困，缺省随机")
    p.add_argument("--seed", type=int, default=None, help="随机种子，可复现")
    return p


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    rng = random.Random(args.seed)

    if args.animal is None:
        animal = rng.choice(sorted(ANIMALS))
    else:
        animal = _norm(args.animal, ANIMAL_ALIASES)
        if animal is None:
            print(f"错误: 无效动物 {args.animal!r}（可选: cat|dog|rabbit 或 猫|狗|兔）",
                  file=sys.stderr)
            return 2

    if args.mood is None:
        mood = rng.choice(sorted(MOODS))
    else:
        mood = _norm(args.mood, MOOD_ALIASES)
        if mood is None:
            print(f"错误: 无效心情 {args.mood!r}"
                  f"（可选: happy|grumpy|sleepy 或 开心|生气|犯困）", file=sys.stderr)
            return 2

    label, art = ARTS[(animal, mood)]
    print(f"[{label}]")
    print("\n".join(art))
    return 0


if __name__ == "__main__":
    sys.exit(main())
