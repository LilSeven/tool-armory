#!/usr/bin/env python3
"""emoji-nickname —— emoji 网名生成器。

用途:
    随机生成符号（emoji、装饰字符）与汉字混排的个性网名，如 "🌙墨染星辰✧"。

示例:
    python emoji-nickname.py              # 随机 1 个
    python emoji-nickname.py -n 5         # 随机 5 个
    python emoji-nickname.py --no-emoji   # 不用 emoji，只用汉字和装饰符号
    python emoji-nickname.py --seed 1     # 固定随机种子，可复现

仅使用 Python 标准库。
"""

import argparse
import random
import sys

EMOJIS = ["✨", "🌙", "⭐", "💫", "🌸", "🍃", "🌊", "🔥", "⚡", "☁️",
          "🦋", "🐱", "🍁", "🔮", "🎧", "🚀", "🍬", "🌺", "🌠", "🪐",
          "🌱", "🎈", "🌀", "❄️"]

DECOS = ["✧", "⋆", "˚", "⊹", "✦", "ღ", "☾", "♡", "˖", "･ﾟ", "｡", "❥"]

CN_HEAD = ["墨染", "云栖", "月白", "星辞", "风眠", "雾里", "拾光", "山雨",
           "青栀", "夜阑", "折月", "枕星", "听澜", "浮生", "半夏", "南絮",
           "迟暮", "清欢", "疏影", "孤鹤"]
CN_TAIL = ["星辰", "旧梦", "未眠", "长安", "南山", "晚风", "听雪", "逐月",
           "揽星", "渡鸦", "归途", "煮酒", "未央", "向晚", "辞晚", "深巷",
           "入海", "过客", "有诗", "无事"]


def _setup_stdio():
    """尽量把 stdout/stderr 切到 UTF-8，避免 Windows 管道下输出报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            if (stream.encoding or "").replace("-", "").lower() != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def generate_nickname(rng, use_emoji=True):
    head = rng.choice(CN_HEAD)
    tail = rng.choice(CN_TAIL)
    dl = rng.choice(DECOS)
    dr = rng.choice(DECOS)
    if use_emoji:
        e = rng.choice(EMOJIS)
        patterns = [
            lambda: e + head + tail + dr,
            lambda: dl + e + head + tail,
            lambda: head + e + tail + dr,
            lambda: dl + head + tail + e,
        ]
    else:
        patterns = [
            lambda: head + tail,
            lambda: dl + head + tail + dr,
            lambda: head + "·" + tail + dr,
        ]
    return rng.choice(patterns)()


def build_parser():
    parser = argparse.ArgumentParser(
        prog="emoji-nickname",
        description="生成符号与汉字混排的个性网名",
    )
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="生成数量（默认 1）")
    parser.add_argument("--no-emoji", action="store_true",
                        help="不使用 emoji，只用汉字和装饰符号")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子（便于复现）")
    return parser


def main(argv=None):
    _setup_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("-n/--count 必须 >= 1")
    rng = random.Random(args.seed)
    for _ in range(args.count):
        print(generate_nickname(rng, use_emoji=not args.no_emoji))
    return 0


if __name__ == "__main__":
    sys.exit(main())
