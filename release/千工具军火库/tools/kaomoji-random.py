#!/usr/bin/env python3
"""颜文字抽签（kaomoji-random）—— 按心情随机抽取颜文字。

用途:
    从「开心 / 生气 / 卖萌」三种心情的颜文字库中随机抽签，
    支持指定心情、一次抽多个、用随机种子复现结果。
    仅用 Python 标准库，单文件即可运行。

示例命令:
    python -I kaomoji-random.py                             # 随机心情抽 1 个
    python -I kaomoji-random.py --mood happy                # 指定心情（happy/开心）
    python -I kaomoji-random.py --mood 生气 -n 3             # 生气颜文字抽 3 个
    python -I kaomoji-random.py --mood cute -n 5 --seed 42  # 固定种子可复现
    python -I kaomoji-random.py --list                      # 列出各心情颜文字数量

参数:
    --mood  happy|angry|cute|开心|生气|卖萌  心情（缺省随机）
    -n, --count N   抽取个数（1-50，默认 1）
    --seed N        随机种子（可复现）
    --list          只列出各心情颜文字数量后退出
"""

import argparse
import random
import sys

MOODS = {
    "happy": {
        "zh": "开心",
        "faces": [
            "(≧▽≦)", "(＾▽＾)", "(＾ω＾)", "ヽ(>∀<☆)ノ", "(＾∀＾)",
            "(o^^o)", "(￣▽￣)ノ", "(=^▽^=)", "(๑•̀ㅂ•́)و", "ヽ(´▽`)ノ",
            "(☆▽☆)", "(≧∇≦)ﾉ", "(＾◡＾)", "(´∀｀)", "(⁎˃ᆺ˂)",
        ],
    },
    "angry": {
        "zh": "生气",
        "faces": [
            "(╬ Ò﹏Ó)", "(＃`Д´)", "(╯°□°）╯︵ ┻━┻", "(￢_￢;)",
            "ヽ(≧Д≦)ノ", "(怒｀Д´怒)", "(¬_¬)", "(>益<)", "(♯▼皿▼)",
            "(＃￣^￣)", "(눈_눈)", "(－‸ლ)", "٩(╬ʘ益ʘ╬)۶", "(ﾒﾟДﾟ)",
        ],
    },
    "cute": {
        "zh": "卖萌",
        "faces": [
            "(◕‿◕)", "(=^･ω･^=)", "(˶ᵔᵕᵔ˶)", "(人 •͈ᴗ•͈)", "ʕ•ᴥ•ʔ",
            "(੭ˊᵕˋ)੭", "(^•ω•^)", "(ᵔᴥᵔ)", "(｡•̀ᴗ-)✧", "(◡ ω ◡)",
            "(✿◠‿◠)", "(´｡• ᵕ •｡)", "(ꈍᴗꈍ)", "( ˘ω˘ )",
        ],
    },
}

ZH2EN = {info["zh"]: key for key, info in MOODS.items()}
VALID_HINT = "happy/angry/cute 或 开心/生气/卖萌"


def norm_mood(raw):
    m = raw.strip().lower()
    return ZH2EN.get(m) or (m if m in MOODS else None)


def build_parser():
    p = argparse.ArgumentParser(
        prog="kaomoji-random", description="按心情随机抽取颜文字（开心/生气/卖萌）"
    )
    p.add_argument("--mood", help="心情: " + VALID_HINT + "，缺省随机")
    p.add_argument("-n", "--count", type=int, default=1, help="抽取个数 1-50，默认 1")
    p.add_argument("--seed", type=int, default=None, help="随机种子，可复现")
    p.add_argument("--list", action="store_true", help="列出各心情颜文字数量后退出")
    return p


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)

    if args.list:
        for key in sorted(MOODS):
            info = MOODS[key]
            print(f"{info['zh']}({key}): {len(info['faces'])} 枚")
        return 0

    if not (1 <= args.count <= 50):
        print("错误: -n/--count 需在 1-50 之间", file=sys.stderr)
        return 2

    rng = random.Random(args.seed)
    if args.mood is None:
        key = rng.choice(sorted(MOODS))
    else:
        key = norm_mood(args.mood)
        if key is None:
            print(f"错误: 无效心情 {args.mood!r}（可选: {VALID_HINT}）", file=sys.stderr)
            return 2

    for _ in range(args.count):
        print(rng.choice(MOODS[key]["faces"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
