#!/usr/bin/env python3
"""词组口令生成器（Diceware 风格）。

用途：
    用 secrets 加密级随机源从内置英文词表中抽取 4-8 个词，拼成易记、
    熵高的词组口令；可自定义分隔符、首字母大写，并可在结尾附加一位
    随机数字。每词熵为 log2(词表大小)，输出时在 stderr 报告估算总熵。

示例命令：
    python passphrase-gen.py                      # 默认 6 个词，'-' 连接
    python passphrase-gen.py -w 8 -c 3            # 8 词，生成 3 条
    python passphrase-gen.py -w 4 -s . --capitalize --number
    python passphrase-gen.py --wordlist eff_big.txt   # 换用自定义词表
                                                      # （如官方 EFF/Diceware 词表）

说明：
    内置词表为人工整理的常见英文词（加载时自动去重并报告实际大小），
    并非官方 EFF/Diceware 词表；如需经典 Diceware 强度（每词 12.9 位），
    请用 --wordlist 指定 7776 词的官方词表。

退出码：
    0 = 成功；2 = 参数或词表错误。

仅依赖 Python 标准库：secrets / argparse / math。
"""

import argparse
import math
import secrets
import sys

WORDLIST_TEXT = """\
ant ape bat bear bee bird boar bull calf cat clam colt crab crow deer doe dog dove duck
eagle eel elk emu falcon finch fish fox frog gnat goat goose gull hare hawk hen heron hog
horse hound hyena ibex jackal jaguar koala lark lion llama lynx mole monkey moose moth
mouse mule newt otter owl panda panther parrot penguin pony puma quail rabbit raccoon
raven robin seal shark sheep skunk snail snake spider squid stag swan tiger toad trout
tuna turtle vulture walrus wasp whale wolf wombat zebra
alder aspen beach birch bloom branch brook bush canyon cave cedar cliff cloud coast creek
dune fern field fjord forest glade gorge grass grove harbor hill iceberg island jungle
lake marsh meadow mesa mist moss mountain oasis ocean palm pebble pond rain reef ridge
river shore spring stone stream summit thunder tide trail valley volcano wave willow wind
anchor anvil basket bell bench bottle box bridge brush bucket candle chair clock coin
comb couch crown cup desk dish door drum fence fork glass hammer handle harp kettle key
knife ladder lamp lantern mirror nail needle net oven pan paper pencil plate pot rope rug
scissors shelf shovel sofa spoon stair table tape tin tool towel tray wagon watch wheel
window
acorn almond apple apricot banana barley basil bean berry butter cabbage candy carrot
celery cheese cherry chili cinnamon clover cocoa coffee corn cream cucumber fig garlic
ginger grape honey kiwi lemon lettuce lime mango maple melon mint mushroom nutmeg oatmeal
onion papaya parsley peach pear peas pepper pickle pumpkin radish raisin rice rosemary
saffron sage salt sesame spinach squash sugar thyme tomato walnut wheat yogurt
amber azure beige black blue brown crimson cyan gold gray green indigo ivory lilac
magenta maroon olive pink purple red silver teal violet white yellow
answer argue arrive bake balance bend blink bounce breathe bring build burn carve chant
chase climb crawl dance decide draw drift drop echo escape explore fade float gather
glide guess hurry imagine inspect juggle kick leap lift listen march measure munch notice
observe paddle paint pause pedal point ponder punch race reach repair rescue row scatter
shuffle signal skate slide sprint stagger stroll swim toss wander whisper wiggle
actor angel artist aunt baker bishop captain chef child clerk coach cousin dancer doctor
driver editor farmer friend ghost giant guard guest hero hunter judge keeper lawyer
leader mayor monk neighbor nurse officer pilot pirate poet police priest prince queen
ranger rider sailor scholar scout singer student teacher theater unicorn village wizard
writer
ember fabric feather fossil gem globe gravel hedge helix helmet hinge hoop horn ink ivy
jet kite knot lens medal meteor nickel orbit piston plank prism quiver radar raft ribbon
rocket rudder sandal shard shell spark spear spiral sprout stem sword tether timber torch
tusk vortex wedge whistle yarn yoke zipper
arrow atlas badge bagel ballot banner barrel basin beetle bicycle blouse bonnet bracelet
bulb bunker cactus camera cannon canvas cellar chapel chapter chest chimney chorus cider
cinema cipher circle clamp clay cloak clown cobalt comet compass copper coral cottage
cotton counter county cover cradle crater crayon crystal cube curtain cushion dagger dawn
deck delta den denim depot dial diary dome donkey donor drain drawer drone dust
fable fiddle flute fountain frost gadget galley garden gateway glacier geyser guitar
hammock haven hollow hotel igloo inlet jar jasmine jewel kayak lagoon lava lodge loom
lute magnet manor marble mill mineral mosaic mural muscle museum noodle orchard orchid
oyster parlor pastry pavilion perch pillar plaza
"""


def load_wordlist(path=None):
    """Return a deduplicated word list from the built-in table or a file."""
    raw = WORDLIST_TEXT
    if path is not None:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    tokens = [tok.lower() for tok in raw.split() if tok and not tok.startswith("#")]
    words = list(dict.fromkeys(tokens))  # dedupe, preserve order
    if len(words) < 16:
        raise ValueError("wordlist too small: %d usable words (need at least 16)"
                         % len(words))
    return words


def generate_passphrase(words, n_words, separator="-", capitalize=False,
                        append_digit=False):
    picked = [secrets.choice(words) for _ in range(n_words)]
    if capitalize:
        picked = [word.capitalize() for word in picked]
    phrase = separator.join(picked)
    if append_digit:
        phrase += str(secrets.randbelow(10))
    return phrase


def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="passphrase-gen",
        description="Diceware-style passphrase generator using secrets (stdlib only).")
    parser.add_argument("-w", "--words", type=int, default=6,
                        help="number of words, 4-8 (default %(default)s)")
    parser.add_argument("-c", "--count", type=int, default=1,
                        help="how many passphrases to generate (default %(default)s)")
    parser.add_argument("-s", "--separator", default="-", metavar="SEP",
                        help="word separator (default '%(default)s')")
    parser.add_argument("--capitalize", action="store_true",
                        help="capitalize the first letter of every word")
    parser.add_argument("--number", action="store_true",
                        help="append one random digit to the last word (+~3.3 bits)")
    parser.add_argument("--wordlist", default=None, metavar="FILE",
                        help="use a custom wordlist file (whitespace-separated words)")
    return parser


def main(argv=None):
    try:
        for stream in (sys.stdout, sys.stderr):
            stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    args = build_arg_parser().parse_args(argv)
    if not 4 <= args.words <= 8:
        print("error: --words must be between 4 and 8", file=sys.stderr)
        return 2
    if not 1 <= args.count <= 1000:
        print("error: --count must be between 1 and 1000", file=sys.stderr)
        return 2

    try:
        words = load_wordlist(args.wordlist)
    except (OSError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    bits = args.words * math.log2(len(words)) + (math.log2(10) if args.number else 0.0)
    for _ in range(args.count):
        print(generate_passphrase(words, args.words, separator=args.separator,
                                  capitalize=args.capitalize,
                                  append_digit=args.number))
    print("wordlist: %d words (%.2f bits/word); entropy ~%.1f bits per passphrase"
          % (len(words), math.log2(len(words)), bits), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
