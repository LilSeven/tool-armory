#!/usr/bin/env python3
"""tmp-name-docker —— 趣味临时名生成器（docker 风格"形容词_科学家"）。

用途:
    随机生成 docker 容器风格的临时名，如 adoring_turing、boring_einstein，
    适合给临时目录、临时文件、git 分支、测试环境或容器命名。

示例:
    python tmp-name-docker.py                  # 随机 1 个名字
    python tmp-name-docker.py -n 5             # 随机 5 个名字
    python tmp-name-docker.py -n 3 --hex 4     # 追加 4 位随机十六进制后缀
    python tmp-name-docker.py --sep=-          # 连接符改为 -，如 adoring-turing
    python tmp-name-docker.py --seed 42        # 固定随机种子，输出可复现

仅使用 Python 标准库。
"""

import argparse
import random
import sys

ADJECTIVES = [
    "admiring", "adoring", "affectionate", "agitated", "amazing", "angry",
    "awesome", "beautiful", "blissful", "bold", "boring", "brave", "busy",
    "charming", "clever", "cool", "compassionate", "competent", "confident",
    "cranky", "dazzling", "determined", "distracted", "dreamy", "eager",
    "eclectic", "elastic", "elated", "elegant", "eloquent", "epic", "exciting",
    "fervent", "festive", "flamboyant", "focused", "friendly", "frosty",
    "funny", "gallant", "gifted", "goofy", "gracious", "great", "happy",
    "hardcore", "heuristic", "hopeful", "hungry", "infallible", "inspiring",
    "interesting", "intelligent", "jolly", "jovial", "keen", "kind",
    "laughing", "loving", "lucid", "magical", "mystifying", "modest", "musing",
    "nervous", "nice", "nifty", "nostalgic", "objective", "optimistic",
    "peaceful", "pedantic", "pensive", "practical", "quirky", "quizzical",
    "relaxed", "reverent", "romantic", "serene", "sharp", "silly", "sleepy",
    "stoic", "strange", "studious", "suspicious", "sweet", "tender",
    "thirsty", "trusting", "unruffled", "upbeat", "vibrant", "vigilant",
    "vigorous", "wizardly", "wonderful", "xenodochial", "youthful", "zealous",
    "zen",
]

SCIENTISTS = [
    "albattani", "allen", "almeida", "archimedes", "aryabhata", "austin",
    "babbage", "banach", "bardeen", "bartik", "bassi", "bell", "benz",
    "bhabha", "bhaskara", "black", "blackwell", "bohr", "booth", "borg",
    "bose", "boyd", "brahmagupta", "brattain", "brown", "celsius",
    "chandrasekhar", "clarke", "cori", "cray", "curie", "darwin", "davinci",
    "dijkstra", "dubinsky", "easley", "edison", "einstein", "elion",
    "engelbart", "euclid", "euler", "faraday", "feistel", "fermat", "fermi",
    "feynman", "franklin", "gagarin", "galileo", "galois", "gates", "gauss",
    "goldberg", "goodall", "gould", "greider", "haibt", "hamilton", "hawking",
    "hellman", "hermann", "herschel", "hertz", "heyrovsky", "hodgkin",
    "hoover", "hopper", "hypatia", "jackson", "jang", "jennings", "jepsen",
    "johnson", "jones", "kalam", "keller", "kepler", "khorana", "kilby",
    "kirch", "knuth", "kowalevski", "lalande", "lamarr", "lamport", "leakey",
    "leavitt", "lewin", "liskov", "lovelace", "lumiere", "mahavira", "mayer",
    "mccarthy", "mcclintock", "mclaren", "mclean", "mendel", "mendeleev",
    "meitner", "mirzakhani", "montalcini", "morse", "murdock", "newton",
    "nightingale", "nobel", "noether", "noyce", "panini", "pascal", "pasteur",
    "payne", "perlman", "pike", "poincare", "poitras", "ptolemy", "raman",
    "ramanujan", "ride", "ritchie", "rhodes", "roentgen", "rubin", "saha",
    "sammet", "shamir", "shannon", "shaw", "shirley", "shockley", "snyder",
    "spence", "stonebraker", "sutherland", "swartz", "swirles", "tesla",
    "thompson", "torvalds", "tu", "turing", "vaughan", "villani", "volhard",
    "wescoff", "wilbur", "wiles", "williams", "williamson", "wilson", "wing",
    "wozniak", "wright", "wu", "yalow", "yonath", "zhukovsky",
]


def _setup_stdio():
    """尽量把 stdout/stderr 切到 UTF-8，避免 Windows 管道下输出报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            if (stream.encoding or "").replace("-", "").lower() != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def build_parser():
    parser = argparse.ArgumentParser(
        prog="tmp-name-docker",
        description='生成 docker 风格"形容词_科学家"随机临时名',
    )
    parser.add_argument("-n", "--count", type=int, default=1,
                        help="生成数量（默认 1）")
    parser.add_argument("--sep", default="_",
                        help="形容词与科学家之间的分隔符（默认 '_'）")
    parser.add_argument("--hex", type=int, default=0, metavar="N",
                        help="在名字后追加 N 位随机十六进制后缀（默认 0）")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子（便于复现）")
    return parser


def generate_names(count, sep, hex_len, rng):
    hex_chars = "0123456789abcdef"
    names = []
    for _ in range(count):
        name = rng.choice(ADJECTIVES) + sep + rng.choice(SCIENTISTS)
        if hex_len > 0:
            name += "-" + "".join(rng.choice(hex_chars) for _ in range(hex_len))
        names.append(name)
    return names


def main(argv=None):
    _setup_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("-n/--count 必须 >= 1")
    if args.hex < 0:
        parser.error("--hex 必须 >= 0")
    rng = random.Random(args.seed)
    for name in generate_names(args.count, args.sep, args.hex, rng):
        print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
